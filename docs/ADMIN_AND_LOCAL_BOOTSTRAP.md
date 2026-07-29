# Admin and Local Bootstrap

The Django admin is a platform operations tool, not a tenant-facing admin
product. A Django superuser can inspect all tenants at:

```
http://localhost:8000/admin/
```

From `backend/`, prepare the database and create a platform superuser:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

`createsuperuser` uses Django's password hashing flow. The platform superuser is
separate from a normal MaritimeOS tenant user and can see platform-wide data.
Staff users without `is_superuser` still require explicit Django model
permissions for each admin model.

## Production safety boundary

Do not expose this development admin deployment to the public internet. The
current repository does not yet provide production controls such as MFA or
SSO enforcement, login rate limiting/lockout, production secret management,
mandatory TLS/HSTS, secure session cookies, restricted `ALLOWED_HOSTS`, or a
production settings module. Before any internet-facing or production use,
those controls must be implemented and reviewed, MFA must be required for
platform administrators, and admin access should be restricted to an
approved private network or equivalent access gateway.

## Local demo data

Create an idempotent demo tenant, application user, default capability roles,
and a Tenant Admin role assignment:

```bash
python manage.py bootstrap_demo
```

The default username is `demo`. A random password is printed once when the
user is first created. An explicit local password can be supplied:

```bash
python manage.py bootstrap_demo --password "local-only-password"
```

Running the command again reuses the existing tenant, user, roles, and
assignment. It does not change the existing password. Password replacement
must be requested explicitly:

```bash
python manage.py bootstrap_demo --reset-password
```

Use `python manage.py bootstrap_demo --help` for tenant, username, email, and
password options. The command refuses to run when Django `DEBUG` is disabled,
and all writes run in one transaction.

The demo user is an application user with tenant capabilities. It is not
`is_staff`, is not a Django superuser, and therefore cannot log in to Django
admin unless platform access is deliberately granted separately.

## Protected operation data

Published, retired, and archived operation template versions are view-only in
admin. Their checklist and workflow definitions cannot be added, edited, or
deleted there. Runtime ServiceRequest, checklist item, workflow step, and
activity records are also view-only so admin cannot bypass domain transition
and audit rules. New draft versions and their definitions remain editable.
