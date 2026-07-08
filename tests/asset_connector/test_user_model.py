from sekoia_automation.asset_connector.models.ocsf.user import (
    LdapPerson,
    User,
)


def test_user_accepts_ldap_person():
    user = User(
        name="john.doe@example.com",
        uid="uid-1",
        ldap_person=LdapPerson(
            job_title="Managing Consultant, Incident Response",
            department="Incident Response",
        ),
    )

    assert user.ldap_person is not None
    assert user.ldap_person.job_title == "Managing Consultant, Incident Response"
    assert user.ldap_person.department == "Incident Response"


def test_user_ldap_person_is_optional():
    user = User(name="jane.doe@example.com", uid="uid-2")

    assert user.ldap_person is None


def test_ldap_person_serializes_only_set_fields():
    user = User(
        name="john.doe@example.com",
        uid="uid-3",
        ldap_person=LdapPerson(job_title="SOC Analyst", department="Security"),
    )

    dumped = user.model_dump(exclude_none=True)

    assert dumped["ldap_person"] == {
        "job_title": "SOC Analyst",
        "department": "Security",
    }


def test_ldap_person_accepts_extended_fields():
    ldap_person = LdapPerson(
        job_title="SOC Analyst",
        department="Security",
        employee_uid="EMP123",
        given_name="John",
        surname="Doe",
        office_location="New York, NY",
    )

    assert ldap_person.employee_uid == "EMP123"
    assert ldap_person.given_name == "John"
    assert ldap_person.surname == "Doe"
    assert ldap_person.office_location == "New York, NY"
