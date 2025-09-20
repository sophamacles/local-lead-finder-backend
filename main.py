import os
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io, csv

load_dotenv()

import scraper  # your scraper.py from earlier
import paypal  # your paypal.py

API_KEY = os.getenv("API_KEY", "dev_key")
ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS", "*")

app = FastAPI(title="Local Lead Finder API (with employee filter & contact export)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOW_ORIGINS.split(",")] if ALLOW_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def require_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# Helper: test if a business matches requested employee range
def _matches_employee_range(business, employee_min, employee_max, strict=False):
    """
    business: dict returned from scraper.find_businesses (has 'employees_tag' and 'employees_estimate')
    Employee min/max: ints or None
    strict: if True, exclude results without any employee info; if False, keep unknowns
    """
    if employee_min is None and employee_max is None:
        return True

    emp_tag = business.get("employees_tag")
    emp_est = business.get("employees_estimate")

    # Try explicit tag first (e.g. '10-50' or '12')
    def parse_tag(v):
        if not v:
            return None
        try:
            if "-" in str(v):
                a,b = str(v).split("-",1)
                return int(a), int(b)
            iv = int(str(v))
            return iv, iv
        except:
            return None

    parsed = parse_tag(emp_tag)
    if parsed:
        pmin, pmax = parsed
        # overlap check
        if employee_min is not None and pmax < employee_min:
            return False
        if employee_max is not None and pmin > employee_max:
            return False
        return True

    # fallback to estimated single integer if present
    if emp_est is not None:
        try:
            est = int(emp_est)
            if employee_min is not None and est < employee_min:
                return False
            if employee_max is not None and est > employee_max:
                return False
            return True
        except:
            pass

    # unknown
    return (not strict)

# Pydantic model for POST search
class SearchRequest(BaseModel):
    category: str
    city_or_address: str | None = None
    lat: float | None = None
    lon: float | None = None
    radius: int = 300
    include_email: bool = False
    include_phone: bool = False
    employee_min: int | None = None
    employee_max: int | None = None
    user_id: str = "guest"
    scrape_limit: int = 5
    strict_employee_filter: bool = False

# Support both GET (quick tests) and POST (frontend)
@app.get("/api/search")
def api_search_get(
    category: str = Query(...),
    city_or_address: str | None = Query(None),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    radius: int = Query(300),
    include_email: bool = Query(False),
    include_phone: bool = Query(False),
    employee_min: int | None = Query(None),
    employee_max: int | None = Query(None),
    user_id: str = Query("guest"),
    scrape_limit: int = Query(5),
    strict_employee_filter: bool = Query(False),
    x_api_key: str = Header(None),
):
    require_api_key(x_api_key)
    # Choose center
    center = None
    if lat is not None and lon is not None:
        center = f"{lat},{lon}"
    elif city_or_address:
        center = city_or_address
    else:
        raise HTTPException(status_code=400, detail="Provide city_or_address OR lat & lon")

    # call scraper: note scraper.find_businesses expects category, city_or_address, size param (we pass 'any')
    results = scraper.find_businesses(category, center, size="any",
                                     user_id=user_id, radius=radius,
                                     email_scrape=include_email, scrape_limit=scrape_limit)

    # filter by employee min/max (post-filter)
    filtered = []
    for b in results:
        if _matches_employee_range(b, employee_min, employee_max, strict=strict_employee_filter):
            # remove fields per include flags
            out = b.copy()
            if not include_email:
                out["email"] = None
            if not include_phone:
                out["phone"] = None
            filtered.append(out)
    return {"count": len(filtered), "results": filtered}

@app.post("/api/search")
def api_search_post(payload: SearchRequest, x_api_key: str = Header(None)):
    require_api_key(x_api_key)
    center = None
    if payload.lat is not None and payload.lon is not None:
        center = f"{payload.lat},{payload.lon}"
    elif payload.city_or_address:
        center = payload.city_or_address
    else:
        raise HTTPException(status_code=400, detail="Provide city_or_address OR lat & lon")

    results = scraper.find_businesses(payload.category, center, size="any",
                                     user_id=payload.user_id, radius=payload.radius,
                                     email_scrape=payload.include_email, scrape_limit=payload.scrape_limit)

    filtered = []
    for b in results:
        if _matches_employee_range(b, payload.employee_min, payload.employee_max, strict=payload.strict_employee_filter):
            out = b.copy()
            if not payload.include_email:
                out["email"] = None
            if not payload.include_phone:
                out["phone"] = None
            filtered.append(out)
    return {"count": len(filtered), "results": filtered}

@app.get("/api/contacts")
def api_contacts(
    category: str = Query(...),
    city_or_address: str | None = Query(None),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    radius: int = Query(300),
    include_email: bool = Query(False),
    include_phone: bool = Query(False),
    employee_min: int | None = Query(None),
    employee_max: int | None = Query(None),
    user_id: str = Query("guest"),
    scrape_limit: int = Query(5),
    strict_employee_filter: bool = Query(False),
    x_api_key: str = Header(None),
):
    require_api_key(x_api_key)
    center = None
    if lat is not None and lon is not None:
        center = f"{lat},{lon}"
    elif city_or_address:
        center = city_or_address
    else:
        raise HTTPException(status_code=400, detail="Provide city_or_address OR lat & lon")

    results = scraper.find_businesses(category, center, size="any",
                                     user_id=user_id, radius=radius,
                                     email_scrape=include_email, scrape_limit=scrape_limit)

    contacts = []
    for r in results:
        if _matches_employee_range(r, employee_min, employee_max, strict=strict_employee_filter):
            contacts.append({
                "name": r.get("name"),
                "phone": r.get("phone") if include_phone else None,
                "email": r.get("email") if include_email else None,
                "website": r.get("website"),
                "lat": r.get("lat"),
                "lon": r.get("lon"),
                "distance_m": r.get("distance_meters")
            })
    return {"count": len(contacts), "contacts": contacts}

@app.get("/api/contacts/export")
def api_contacts_export(
    category: str = Query(...),
    city_or_address: str | None = Query(None),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    radius: int = Query(300),
    include_email: bool = Query(False),
    include_phone: bool = Query(False),
    employee_min: int | None = Query(None),
    employee_max: int | None = Query(None),
    user_id: str = Query("guest"),
    scrape_limit: int = Query(5),
    strict_employee_filter: bool = Query(False),
    x_api_key: str = Header(None),
):
    require_api_key(x_api_key)
    center = None
    if lat is not None and lon is not None:
        center = f"{lat},{lon}"
    elif city_or_address:
        center = city_or_address
    else:
        raise HTTPException(status_code=400, detail="Provide city_or_address OR lat & lon")

    results = scraper.find_businesses(category, center, size="any",
                                     user_id=user_id, radius=radius,
                                     email_scrape=include_email, scrape_limit=scrape_limit)

    contacts = []
    for r in results:
        if _matches_employee_range(r, employee_min, employee_max, strict=strict_employee_filter):
            contacts.append({
                "name": r.get("name", ""),
                "phone": r.get("phone") or "",
                "email": r.get("email") or "",
                "website": r.get("website") or ""
            })

    # Build CSV in-memory
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["name", "phone", "email", "website"])
    writer.writeheader()
    writer.writerows(contacts)
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=contacts.csv"})

# PayPal endpoints (unchanged)
@app.post("/api/subscriptions/create")
def api_create_sub(plan_id: str = Body(...), return_url: str = Body(...), cancel_url: str = Body(...), x_api_key: str = Header(None)):
    require_api_key(x_api_key)
    try:
        sub = paypal.create_subscription(plan_id, return_url, cancel_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PayPal error: {e}")
    return sub

@app.get("/api/subscriptions/status")
def api_sub_status(subscription_id: str = Query(...), x_api_key: str = Header(None)):
    require_api_key(x_api_key)
    try:
        status = paypal.get_subscription_status(subscription_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PayPal error: {e}")
    return status

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
