from fastapi import APIRouter

from app.api.v1.auth import auth_router
from app.api.v1.boarding import boarding_router
from app.api.v1.buses import buses_router
from app.api.v1.payments import payments_router
from app.api.v1.reservations import reservations_router
from app.api.v1.routes import routes_router
from app.api.v1.stations import stations_router
from app.api.v1.subscription_plans import subscription_plans_router
from app.api.v1.subscriptions import subscriptions_router
from app.api.v1.trips import trips_router
from app.api.v1.universities import universities_router
from app.api.v1.users import users_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_v1_router.include_router(users_router, prefix="/users", tags=["Users"])
api_v1_router.include_router(
    universities_router, prefix="/universities", tags=["Universities"]
)
api_v1_router.include_router(buses_router, prefix="/buses", tags=["Buses"])
api_v1_router.include_router(stations_router, prefix="/stations", tags=["Stations"])
api_v1_router.include_router(routes_router, prefix="/routes", tags=["Routes"])
api_v1_router.include_router(trips_router, prefix="/trips", tags=["Trips"])
api_v1_router.include_router(
    reservations_router, prefix="/reservations", tags=["Reservations"]
)
api_v1_router.include_router(payments_router, prefix="/payments", tags=["Payments"])
api_v1_router.include_router(
    subscription_plans_router,
    prefix="/subscription-plans",
    tags=["Subscription Plans"],
)
api_v1_router.include_router(
    subscriptions_router, prefix="/subscriptions", tags=["Subscriptions"]
)
api_v1_router.include_router(
    boarding_router, prefix="/boarding", tags=["Boarding"]
)
