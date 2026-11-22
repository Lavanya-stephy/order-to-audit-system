from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import Role

User = get_user_model()


class RoleAccessControlTests(TestCase):
    def setUp(self):
        self.password = 'Pass123!@#'

        # Create one user for each business role
        self.salesman = User.objects.create_user(
            username='salesman_user',
            password=self.password,
            role=Role.SALESMAN,
        )
        self.admin = User.objects.create_user(
            username='admin_user',
            password=self.password,
            role=Role.ADMIN,
        )
        self.production = User.objects.create_user(
            username='production_user',
            password=self.password,
            role=Role.PRODUCTION,
        )
        self.accountant = User.objects.create_user(
            username='accountant_user',
            password=self.password,
            role=Role.ACCOUNTANT,
        )
        self.owner = User.objects.create_user(
            username='owner_user',
            password=self.password,
            role=Role.OWNER,
        )
        self.superuser = User.objects.create_superuser(
            username='super_user',
            password=self.password,
            role=Role.ADMIN,
        )

        self.endpoints = {
            Role.SALESMAN: reverse('salesman_dashboard'),
            Role.ADMIN: reverse('admin_dashboard'),
            Role.PRODUCTION: reverse('production_dashboard'),
            Role.ACCOUNTANT: reverse('accountant_dashboard'),
            Role.OWNER: reverse('owner_dashboard'),
        }

    # --- Model Tests ---
    def test_user_role_properties(self):
        """Verify role-checking helper properties on the User model."""
        self.assertTrue(self.salesman.is_salesman)
        self.assertFalse(self.salesman.is_factory_admin)

        self.assertTrue(self.admin.is_factory_admin)
        self.assertFalse(self.admin.is_production)

        self.assertTrue(self.production.is_production)
        self.assertFalse(self.production.is_accountant)

        self.assertTrue(self.accountant.is_accountant)
        self.assertFalse(self.accountant.is_owner)

        self.assertTrue(self.owner.is_owner)
        self.assertFalse(self.owner.is_salesman)

        self.assertTrue(self.superuser.is_factory_admin)

    # --- Unauthenticated Access Tests ---
    def test_unauthenticated_redirects_to_login(self):
        """Unauthenticated requests to protected endpoints must redirect to login."""
        for role, url in self.endpoints.items():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse('login')))

    def test_root_redirects_to_login_when_unauthenticated(self):
        """Unauthenticated request to '/' redirects to login."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))

    # --- Role-Based Login Redirect Tests ---
    def test_role_based_login_redirects(self):
        """Each role must be redirected to its specific dashboard upon login."""
        users_and_expected_urls = [
            (self.salesman, self.endpoints[Role.SALESMAN]),
            (self.admin, self.endpoints[Role.ADMIN]),
            (self.production, self.endpoints[Role.PRODUCTION]),
            (self.accountant, self.endpoints[Role.ACCOUNTANT]),
            (self.owner, self.endpoints[Role.OWNER]),
        ]

        for user, expected_url in users_and_expected_urls:
            client = Client()
            response = client.post(reverse('login'), {
                'username': user.username,
                'password': self.password,
            })
            self.assertRedirects(response, expected_url)

    def test_authenticated_root_redirects_to_role_dashboard(self):
        """Authenticated users visiting '/' or '/dashboard/' are redirected to their own dashboard."""
        client = Client()
        client.login(username=self.production.username, password=self.password)
        response = client.get(reverse('home'))
        self.assertRedirects(response, self.endpoints[Role.PRODUCTION])

    # --- Permission & Access Isolation Tests ---
    def test_salesman_access_isolation(self):
        """Salesman can only access salesman dashboard; others yield 403."""
        client = Client()
        client.login(username=self.salesman.username, password=self.password)

        # Authorized
        res = client.get(self.endpoints[Role.SALESMAN])
        self.assertEqual(res.status_code, 200)

        # Unauthorized
        for role in [Role.ADMIN, Role.PRODUCTION, Role.ACCOUNTANT, Role.OWNER]:
            res = client.get(self.endpoints[role])
            self.assertEqual(res.status_code, 403)

    def test_admin_access_isolation(self):
        """Factory Admin can access admin dashboard; other role pages yield 403."""
        client = Client()
        client.login(username=self.admin.username, password=self.password)

        res = client.get(self.endpoints[Role.ADMIN])
        self.assertEqual(res.status_code, 200)

        for role in [Role.SALESMAN, Role.PRODUCTION, Role.ACCOUNTANT, Role.OWNER]:
            res = client.get(self.endpoints[role])
            self.assertEqual(res.status_code, 403)

    def test_production_access_isolation(self):
        """Production supervisor can access production dashboard; others yield 403."""
        client = Client()
        client.login(username=self.production.username, password=self.password)

        res = client.get(self.endpoints[Role.PRODUCTION])
        self.assertEqual(res.status_code, 200)

        for role in [Role.SALESMAN, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER]:
            res = client.get(self.endpoints[role])
            self.assertEqual(res.status_code, 403)

    def test_accountant_access_isolation(self):
        """Accountant can access auditor/accountant dashboard; others yield 403."""
        client = Client()
        client.login(username=self.accountant.username, password=self.password)

        res = client.get(self.endpoints[Role.ACCOUNTANT])
        self.assertEqual(res.status_code, 200)

        for role in [Role.SALESMAN, Role.ADMIN, Role.PRODUCTION, Role.OWNER]:
            res = client.get(self.endpoints[role])
            self.assertEqual(res.status_code, 403)

    def test_owner_access_isolation(self):
        """Owner can access owner dashboard; others yield 403."""
        client = Client()
        client.login(username=self.owner.username, password=self.password)

        res = client.get(self.endpoints[Role.OWNER])
        self.assertEqual(res.status_code, 200)

        for role in [Role.SALESMAN, Role.ADMIN, Role.PRODUCTION, Role.ACCOUNTANT]:
            res = client.get(self.endpoints[role])
            self.assertEqual(res.status_code, 403)

    def test_superuser_access_all_dashboards(self):
        """Superuser has access to all dashboards."""
        client = Client()
        client.login(username=self.superuser.username, password=self.password)

        for role, url in self.endpoints.items():
            res = client.get(url)
            self.assertEqual(res.status_code, 200)

    # --- Logout Test ---
    def test_logout_clears_session(self):
        """Logout should clear user session and redirect to login."""
        client = Client()
        client.login(username=self.salesman.username, password=self.password)
        res = client.post(reverse('logout'))
        self.assertEqual(res.status_code, 302)
        # Attempting protected access after logout should redirect to login
        res = client.get(self.endpoints[Role.SALESMAN])
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.url.startswith(reverse('login')))
