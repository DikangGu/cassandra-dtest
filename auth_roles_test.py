import time

from cql import ProgrammingError
from cql.cassandra.ttypes import AuthenticationException
from dtest import Tester, debug
from tools import *
from nose.tools import nottest

class TestAuth(Tester):

    def __init__(self, *args, **kwargs):
        self.ignore_log_patterns = [
            # This one occurs if we do a non-rolling upgrade, the node
            # it's trying to send the migration to hasn't started yet,
            # and when it does, it gets replayed and everything is fine.
            r'Can\'t send migration request: node.*is down',
        ]
        Tester.__init__(self, *args, **kwargs)

    def create_drop_role_test(self):
        self.prepare()
        cursor = self.get_cursor(user='cassandra', password='cassandra')

        cursor.execute("LIST ROLES")
        self.assertEqual(0, cursor.rowcount)

        cursor.execute("CREATE ROLE role1")

        cursor.execute("LIST ROLES")
        self.assertEqual(1, cursor.rowcount) # role1

        cursor.execute("DROP ROLE role1")

        cursor.execute("LIST ROLES")
        self.assertEqual(0, cursor.rowcount)

    def conditional_create_drop_role_test(self):
        self.prepare()
        cursor = self.get_cursor(user='cassandra', password='cassandra')

        cursor.execute("LIST ROLES")
        self.assertEqual(0, cursor.rowcount)

        cursor.execute("CREATE ROLE IF NOT EXISTS role1")
        cursor.execute("CREATE ROLE IF NOT EXISTS role1")

        cursor.execute("LIST ROLES")
        self.assertEqual(1, cursor.rowcount) # role1

        cursor.execute("DROP ROLE IF EXISTS role1")
        cursor.execute("DROP ROLE IF EXISTS role1")

        cursor.execute("LIST ROLES")
        self.assertEqual(0, cursor.rowcount)

    def create_drop_role_validation_test(self):
        self.prepare()

        cassandra = self.get_cursor(user='cassandra', password='cassandra')
        cassandra.execute("CREATE USER mike WITH PASSWORD '12345' NOSUPERUSER")
        mike = self.get_cursor(user='mike', password='12345')

        self.assertUnauthorized("Only superusers are allowed to perform CREATE ROLE queries", mike, 'CREATE ROLE role2')

        cassandra.execute("CREATE ROLE role1")

        self.assertUnauthorized("Only superusers are allowed to perform DROP ROLE queries", mike, 'DROP ROLE role1')

        self.assertUnauthorized("Role role1 already exists", cassandra, 'CREATE ROLE role1')

        cassandra.execute("DROP ROLE role1")

        self.assertUnauthorized("Role role1 doesn't exist", cassandra, 'DROP ROLE role1')

    def grant_revoke_roles_test(self):
        self.prepare()

        cassandra = self.get_cursor(user='cassandra', password='cassandra')
        cassandra.execute("CREATE USER mike WITH PASSWORD '12345' NOSUPERUSER")
        cassandra.execute("CREATE ROLE role1")
        cassandra.execute("CREATE ROLE role2")

        cassandra.execute("GRANT ROLE role1 TO USER mike")
        
        self.assertRoles(['role1'], cassandra, 'LIST ROLES OF USER mike')

        cassandra.execute("GRANT ROLE role1 TO ROLE role2")
        
        self.assertRoles(['role1'], cassandra, 'LIST ROLES OF ROLE role2')

        cassandra.execute("REVOKE ROLE role1 FROM USER mike")

        self.assertRoles([], cassandra, 'LIST ROLES OF USER mike')

        cassandra.execute("REVOKE ROLE role1 FROM ROLE role2")

        self.assertRoles([], cassandra, 'LIST ROLES OF ROLE role2')

    def grant_revoke_role_validation_test(self):
        self.prepare()

        cassandra = self.get_cursor(user='cassandra', password='cassandra')
        cassandra.execute("CREATE USER mike WITH PASSWORD '12345' NOSUPERUSER")
        mike = self.get_cursor(user='mike', password='12345')

        self.assertUnauthorized("Role role1 doesn't exist", cassandra, 'GRANT ROLE role1 TO USER mike')

        cassandra.execute("CREATE ROLE role1")
        
        self.assertUnauthorized("A role cannot operate on itself", cassandra, 'GRANT ROLE role1 TO ROLE role1')

        self.assertUnauthorized("Role role2 doesn't exist", cassandra, 'GRANT ROLE role1 TO ROLE role2')
        self.assertUnauthorized("User john doesn't exist", cassandra, 'GRANT ROLE role1 TO USER john')

        cassandra.execute("CREATE USER john WITH PASSWORD '12345' NOSUPERUSER")
        cassandra.execute("CREATE ROLE role2")
        cassandra.execute("GRANT ROLE role1 TO ROLE role2")
        
        self.assertUnauthorized('Role role2 is already granted Role role1', cassandra, 'GRANT ROLE role1 TO ROLE role2')

        self.assertUnauthorized('Grant will create circular dependency', cassandra, 'GRANT ROLE role2 TO ROLE role1')

        cassandra.execute("REVOKE ROLE role1 FROM ROLE role2")

        self.assertUnauthorized('Role role1 is not granted to Role role2', cassandra, 'REVOKE ROLE role1 FROM ROLE role2')

        self.assertUnauthorized('Only superusers are allowed to perform role management queries', mike, 'GRANT ROLE role1 TO USER john')

        cassandra.execute("GRANT ROLE role1 TO USER john")

        self.assertUnauthorized('Only superusers are allowed to perform role management queries', mike, 'REVOKE ROLE role1 FROM USER john')

        self.assertUnauthorized('Only superusers are allowed to perform role management queries', mike, 'GRANT ROLE role1 TO ROLE role2')
        
        cassandra.execute("GRANT ROLE role1 TO ROLE role2")

        self.assertUnauthorized('Only superusers are allowed to perform role management queries', mike, 'REVOKE ROLE role1 FROM ROLE role2')

    def list_roles_test(self):
        self.prepare()

        cassandra = self.get_cursor(user='cassandra', password='cassandra')
        cassandra.execute("CREATE USER mike WITH PASSWORD '12345' NOSUPERUSER")
        mike = self.get_cursor(user='mike', password='12345')

        cassandra.execute("CREATE ROLE role1")
        cassandra.execute("CREATE ROLE role2")
        cassandra.execute("CREATE ROLE role3")
        cassandra.execute("CREATE ROLE role4")

        self.assertRoles(['role1', 'role2', 'role3', 'role4'], cassandra, 'LIST ROLES')

        cassandra.execute("GRANT ROLE role1 TO ROLE role2")
        cassandra.execute("GRANT ROLE role2 TO ROLE role3")

        cassandra.execute("GRANT ROLE role3 TO USER mike")
        cassandra.execute("GRANT ROLE role4 TO USER mike")

        self.assertRoles(['role1', 'role2'], cassandra, 'LIST ROLES OF ROLE role3')

        self.assertRoles(['role2'], cassandra, 'LIST ROLES OF ROLE role3 NORECURSIVE')

        self.assertRoles(['role1', 'role2', 'role3', 'role4'], cassandra, 'LIST ROLES OF USER mike')

        self.assertRoles(['role3', 'role4'], cassandra, 'LIST ROLES OF USER mike NORECURSIVE')

        self.assertRoles(['role1', 'role2', 'role3', 'role4'], mike, 'LIST ROLES')

        self.assertRoles(['role3', 'role4'], mike, 'LIST ROLES NORECURSIVE')

    def list_roles_validation_test(self):
        self.prepare()

        cassandra = self.get_cursor(user='cassandra', password='cassandra')
        cassandra.execute("CREATE USER mike WITH PASSWORD '12345' NOSUPERUSER")
        mike = self.get_cursor(user='mike', password='12345')

        cassandra.execute("CREATE ROLE role1")
        cassandra.execute("CREATE ROLE role2")
        cassandra.execute("CREATE ROLE role3")
        cassandra.execute("CREATE ROLE role4")

        cassandra.execute("GRANT ROLE role1 TO ROLE role2")
        cassandra.execute("GRANT ROLE role2 TO ROLE role3")

        cassandra.execute("GRANT ROLE role3 TO USER mike")
        cassandra.execute("GRANT ROLE role4 TO USER mike")
        
        self.assertUnauthorized('Only superusers are allowed to LIST ROLES for another user or role', mike, 'LIST ROLES OF ROLE role3')
        self.assertUnauthorized('Only superusers are allowed to LIST ROLES for another user or role', mike, 'LIST ROLES OF USER mike')

    def grant_revoke_permissions_test(self):
        self.prepare()

        cassandra = self.get_cursor(user='cassandra', password='cassandra')
        cassandra.execute("CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy', 'replication_factor':1}")
        cassandra.execute("CREATE TABLE ks.cf (id int primary key, val int)")
        cassandra.execute("CREATE USER mike WITH PASSWORD '12345' NOSUPERUSER")
        cassandra.execute("CREATE ROLE role1")

        cassandra.execute("GRANT ALL ON table ks.cf TO ROLE role1")
        cassandra.execute("GRANT ROLE role1 TO USER mike")

        mike = self.get_cursor(user='mike', password='12345')
        
        mike.execute("INSERT INTO ks.cf (id, val) VALUES (0, 0)")
        mike.execute("SELECT * FROM ks.cf")
        self.assertEquals(1, mike.rowcount)

        cassandra.execute("REVOKE ROLE role1 FROM USER mike")

        # Role changes only take effect after logging out and back in
        mike = self.get_cursor(user='mike', password='12345')
        
        self.assertUnauthorized("User mike has no MODIFY permission on <table ks.cf> or any of its parents", mike, "INSERT INTO ks.cf (id, val) VALUES (0, 0)")
        
        cassandra.execute("GRANT ROLE role1 TO USER mike")
        cassandra.execute("REVOKE ALL ON ks.cf FROM ROLE role1")
        
        self.assertUnauthorized("User mike has no MODIFY permission on <table ks.cf> or any of its parents", mike, "INSERT INTO ks.cf (id, val) VALUES (0, 0)")

    def list_permissions_test(self):
        self.prepare()

        cassandra = self.get_cursor(user='cassandra', password='cassandra')
        cassandra.execute("CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy', 'replication_factor':1}")
        cassandra.execute("CREATE TABLE ks.cf (id int primary key, val int)")
        cassandra.execute("CREATE USER mike WITH PASSWORD '12345' NOSUPERUSER")
        cassandra.execute("CREATE ROLE role1")

        cassandra.execute("GRANT SELECT ON table ks.cf TO ROLE role1")
        cassandra.execute("GRANT MODIFY ON table ks.cf TO USER mike")

        cassandra.execute("GRANT ROLE role1 TO USER mike")
        
        self.assertPermissionsListed([('mike', 'None', '<table ks.cf>', 'MODIFY'),
                                      ('None', 'role1', '<table ks.cf>', 'SELECT')],
                                     cassandra, "LIST ALL PERMISSIONS")

        mike = self.get_cursor(user='mike', password='12345')
        
        self.assertPermissionsListed([('mike', 'None', '<table ks.cf>', 'MODIFY'),
                                      ('None', 'role1', '<table ks.cf>', 'SELECT')],
                                     mike, "LIST ALL PERMISSIONS")
        

    def prepare(self, nodes=1, permissions_expiry=0):
        config = {'authenticator' : 'org.apache.cassandra.auth.RoleAwarePasswordAuthenticator',
                  'authorizer' : 'org.apache.cassandra.auth.CassandraRoleAwareAuthorizer',
                  'permissions_validity_in_ms' : permissions_expiry}
        self.cluster.set_configuration_options(values=config)
        self.cluster.populate(nodes).start(no_wait=True)
        # default user setup is delayed by 10 seconds to reduce log spam
        
        if nodes == 1:
            self.cluster.nodelist()[0].watch_log_for('Created default superuser')
        else:
            # can' just watch for log - the line will appear in just one of the nodes' logs
            # only one test uses more than 1 node, though, so some sleep is fine.
            time.sleep(15)

    def get_cursor(self, node_idx=0, user=None, password=None):
        node = self.cluster.nodelist()[node_idx]
        conn = self.cql_connection(node, version="3.1.7", user=user, password=password)
        return conn.cursor()

    def assertPermissionsListed(self, expected, cursor, query):
        cursor.execute(query)
        perms = [(str(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in cursor.fetchall()]
        self.assertEqual(sorted(expected), sorted(perms))

    def assertRoles(self, expected, cursor, query):
        cursor.execute(query)
        roles = [(r[0]) for r in cursor.fetchall()]
        self.assertEqual(sorted(expected), sorted(roles))

    def assertUnauthorized(self, message, cursor, query):
        with self.assertRaises(ProgrammingError) as cm:
            cursor.execute(query)
        self.assertEqual("Bad Request: " + message, cm.exception.message)
