from sqlalchemy.orm import Session

from app.models.pickup_point import PickupPoint
from app.repositories.route_repository import RouteRepository


def test_route_repository_create_and_get(db_session: Session) -> None:
    repo = RouteRepository(db_session)

    route = repo.create(
        name="Campus Express",
        is_active=True,
    )

    assert route.id is not None
    assert route.name == "Campus Express"
    assert route.is_active is True

    # Get by ID
    fetched = repo.get_by_id(route.id)
    assert fetched is not None
    assert fetched.id == route.id

    # Get by name
    by_name = repo.get_by_name("Campus Express")
    assert by_name is not None
    assert by_name.id == route.id

    # Exists check
    assert repo.exists_by_name("Campus Express") is True
    assert repo.exists_by_name("campus express") is False  # exact match only
    assert repo.exists_by_name("Route 999") is False
    assert repo.exists_by_name("Campus Express", exclude_id=route.id) is False


def test_route_repository_list_and_search(db_session: Session) -> None:
    repo = RouteRepository(db_session)

    r1 = repo.create("Alpha Line", is_active=True)
    r2 = repo.create("Beta Line", is_active=False)

    # List all
    routes, total = repo.list(page=1, page_size=10)
    assert total == 2
    assert len(routes) == 2

    # Filter active
    active_routes, active_total = repo.list(is_active=True)
    assert active_total == 1
    assert active_routes[0].id == r1.id

    # Search
    searched, search_total = repo.list(search="beta")
    assert search_total == 1
    assert searched[0].id == r2.id


def test_route_repository_update_and_delete(db_session: Session) -> None:
    repo = RouteRepository(db_session)

    route = repo.create("Old Route")

    updated = repo.update(
        route=route,
        name="New Route",
        is_active=False,
    )
    assert updated.name == "New Route"
    assert updated.is_active is False

    repo.delete(route)
    assert repo.get_by_id(route.id) is None


def test_route_repository_points_loaded_with_route(db_session: Session) -> None:
    """Route is a container of pickup points; points are eager-loaded."""
    repo = RouteRepository(db_session)
    route = repo.create("Container Route")

    from app.repositories.pickup_point_repository import PickupPointRepository

    point_repo = PickupPointRepository(db_session)
    p1 = point_repo.create(route_id=route.id, name="Point A", sequence=1)
    p2 = point_repo.create(route_id=route.id, name="Point B", sequence=2)

    fetched = repo.get_by_id(route.id)
    assert fetched is not None
    point_ids = [p.id for p in fetched.pickup_points]
    assert point_ids == [p1.id, p2.id]
