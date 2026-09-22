"""
Integration tests for Flask application routes and database models.
"""
import pytest
from app import app, db
from models import Job, Profile, AuditLog, TrackedCompany


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    with app.app_context():
        db.create_all()
        p = Profile(full_name="Tester", email="test@example.com")
        db.session.add(p)
        db.session.commit()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_index_route(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Multi-Portal Job Discovery" in response.data
    assert b"Discovered Job Postings" in response.data


def test_audit_route(client):
    response = client.get("/audit")
    assert response.status_code == 200
    assert b"System Application Audit Trail" in response.data


def test_report_route(client):
    response = client.get("/report")
    assert response.status_code == 200
    assert b"Application Outcomes" in response.data


def test_portals_crud(client):
    # Add portal
    post_res = client.post("/portals/add", data={
        "display_name": "TestCompany",
        "ats_type": "ashby",
        "board_token": "testslug",
    }, follow_redirects=True)
    assert post_res.status_code == 200
    assert b"TestCompany" in post_res.data

    with app.app_context():
        co = TrackedCompany.query.filter_by(display_name="TestCompany").first()
        assert co is not None
        assert co.ats_type == "ashby"

        # Delete portal
        del_res = client.post(f"/portals/{co.id}/delete", follow_redirects=True)
        assert del_res.status_code == 200
        assert TrackedCompany.query.filter_by(display_name="TestCompany").first() is None


def test_profile_update(client):
    res = client.post("/profile", data={
        "full_name": "Rajesh Kumar",
        "email": "rajesh@example.com",
        "phone": "+91 9988776655",
        "total_experience_years": "5",
        "current_ctc": "20 LPA",
        "expected_ctc": "30 LPA",
        "custom_key": ["relocation"],
        "custom_val": ["Willing to relocate to Bangalore"],
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        profile = Profile.query.first()
        assert profile.full_name == "Rajesh Kumar"
        assert profile.get_custom_answers().get("relocation") == "Willing to relocate to Bangalore"
