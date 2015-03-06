import random, re, time, uuid
from dtest import Tester, debug
from tools import since
from assertions import assert_one, assert_invalid, assert_none
from cassandra import InvalidRequest, ConsistencyLevel
from cassandra.query import BatchStatement, SimpleStatement
from cassandra.protocol import ConfigurationException
from tools import since, new_node

class TestGlobalIndexes(Tester):

    def prepare(self):
        cluster = self.cluster
        cluster.populate(3).start()
        node1, node2, node3 = cluster.nodelist()

        session = self.patient_cql_connection(node1)
        self.create_ks(session, 'ks', 1)
        return session

    def carl_prepare(self):
        cluster.populate(3).start()
        node1 = cluster.nodelist()[0]

        cursor = self.patient_cql_connection(node1)
        self.create_ks(cursor, 'ks', 1)
        columns = {"password": "varchar", "gender": "varchar", "session_token": "varchar", "state": "varchar", "birth_year": "bigint"}
        self.create_cf(cursor, 'users', columns=columns)

        # create index
        cursor.execute("CREATE GLOBAL INDEX ON ks.users (state) DENORMALIZED (password, session_token);")

        return cursor

    @since('3.0')
    def populate_index_after_insert_test(self):
        session = self.prepare()
        session.execute("CREATE TABLE t (id int PRIMARY KEY, v int)")

        for i in xrange(10000):
            session.execute("INSERT INTO t (id, v) VALUES (%d, %d)" % (i, i))

        session.execute("CREATE INDEX ON t (v)")

        #Should not be able to query an index until it is built.
        for i in xrange(10000):
            try:
                assert_one(session, "SELECT * FROM t WHERE v = %d" % i, [i, i])
            except InvalidRequest as e:
                assert re.search("Cannot query index until it is built.", str(e))

    @since('3.0')
    def drop_index_test(self):
        session = self.prepare()
        session.execute("CREATE TABLE t (id int PRIMARY KEY, v int)")
        session.execute("CREATE INDEX ON t (v)")

        for i in xrange(1000):
            session.execute("INSERT INTO t (id, v) VALUES (%d, %d)" % (i, i))

        for i in xrange(1000):
            assert_one(session, "SELECT * FROM t WHERE v = %d" % i, [i, i])

        session.execute("DROP INDEX ks.t_v_idx")

        for i in xrange(1000):
            assert_invalid(session, "SELECT * FROM t WHERE v = %d" % i)

    @since('3.0')
    def test_6924_dropping_cf(self):
        session = self.prepare()

        for i in xrange(10):
            try:
                session.execute("DROP TABLE t")
            except InvalidRequest:
                pass

            session.execute("CREATE TABLE t (id int PRIMARY KEY, v int)")
            session.execute("CREATE INDEX ON t (v)")

            for i in xrange(10):
                session.execute("INSERT INTO t (id, v) VALUES (%d, 0)" % i)

            rows = session.execute("select count(*) from t WHERE v=0")
            count = rows[0][0]
            self.assertEqual(count, 10)

    @since('3.0')
    def add_node_after_index_test(self):
        session = self.prepare()
        session.execute("CREATE TABLE t (id int PRIMARY KEY, v int)")
        session.execute("CREATE INDEX ON t (v)")

        for i in xrange(1000):
            session.execute("INSERT INTO t (id, v) VALUES (%d, %d)" % (i, i))

        for i in xrange(1000):
            assert_one(session, "SELECT * FROM t WHERE v = %d" % i, [i, i])

        node4 = new_node(self.cluster)
        node4.start()

        session2 = self.patient_exclusive_cql_connection(node4)

        for i in xrange(1000):
            assert_one(session2, "SELECT * FROM ks.t WHERE v = %d" % i, [i, i])

        for i in xrange(1000, 1100):
            session.execute("INSERT INTO t (id, v) VALUES (%d, %d)" % (i, i))

        for i in xrange(1000, 1100):
            assert_one(session, "SELECT * FROM t WHERE v = %d" % i, [i, i])

    @since('3.0')
    def drop_node_after_index_test(self):
        session = self.prepare()
        session.execute("CREATE TABLE t (id int PRIMARY KEY, v int)")
        session.execute("CREATE INDEX ON t (v)")

        for i in xrange(1000):
            session.execute("INSERT INTO t (id, v) VALUES (%d, %d)" % (i, i))

        for i in xrange(1000):
            assert_one(session, "SELECT * FROM t WHERE v = %d" % i, [i, i])

        node3 = self.cluster.nodelist()[2]
        node3.nodetool("decommission")
        self.cluster.remove(node3)

        for i in xrange(1000):
            assert_one(session, "SELECT * FROM ks.t WHERE v = %d" % i, [i, i])

        for i in xrange(1000, 1100):
            session.execute("INSERT INTO t (id, v) VALUES (%d, %d)" % (i, i))

        for i in xrange(1000, 1100):
            assert_one(session, "SELECT * FROM t WHERE v = %d" % i, [i, i])

    @since('3.0')
    def add_dc_after_index_test(self):
        session = self.prepare()
        session.execute("CREATE TABLE t (id int PRIMARY KEY, v int)")
        session.execute("CREATE INDEX ON t (v)")

        for i in xrange(1000):
            session.execute("INSERT INTO t (id, v) VALUES (%d, %d)" % (i, i))

        for i in xrange(1000):
            assert_one(session, "SELECT * FROM t WHERE v = %d" % i, [i, i])

        node4 = new_node(self.cluster, data_center='dc2')
        node4.start()
        node5 = new_node(self.cluster, remote_debug_port='2500', data_center='dc2')
        node5.start()

        session2 = self.patient_exclusive_cql_connection(node4)

        for i in xrange(1000):
            assert_one(session2, "SELECT * FROM ks.t WHERE v = %d" % i, [i, i])

        for i in xrange(1000, 1100):
            session.execute("INSERT INTO t (id, v) VALUES (%d, %d)" % (i, i))

        for i in xrange(1000, 1100):
            assert_one(session, "SELECT * FROM t WHERE v = %d" % i, [i, i])

    @since('3.0')
    def test_8272(self):
        session = self.prepare()
        session.execute("CREATE TABLE t (id int PRIMARY KEY, v text)")
        session.execute("CREATE INDEX ON t (v)")

        for i in xrange(1000):
            session.execute("INSERT INTO t (id, v) VALUES (0, 'foo%s')" % i)

        for i in xrange(1000):
            insert_query = SimpleStatement("UPDATE t SET v = 'bar%s' WHERE id = 0" % i, ConsistencyLevel.QUORUM)

            session.execute(insert_query)
            assert_none(session, "SELECT * from t WHERE v = 'foo%s'" % i, ConsistencyLevel.QUORUM)


    ##BASIC TESTS. COPY 2i tests from cql_tests here

    @since('3.0')
    def global_index_test(self):
        session = self.prepare()
        session.execute("CREATE TABLE t (id int PRIMARY KEY, v int)")
        session.execute("CREATE INDEX ON t (v)")

        for i in xrange(1000):
            session.execute("INSERT INTO t (id, v) VALUES (%d, %d)" % (i, i))

        for i in xrange(1000):
            assert_one(session, "SELECT * FROM t WHERE v = %d" % i, [i, i])

    @since('3.0')
    def test_create_index(self):
        cursor = self.carl_prepare()

        result = cursor.execute("SELECT * FROM system.schema_globalindexes WHERE keyspace_name='ks' AND columnfamily_name='users'")
        assert len(result) == 1, "Expecting 1 global index, got" + str(result)


    @since('3.0')
    def test_index_insert(self):
        cursor = self.carl_prepare()

        # insert data
        cursor.execute("INSERT INTO users (KEY, password, gender, state, birth_year) VALUES ('user1', 'ch@ngem3a', 'f', 'TX', 1968);")
        cursor.execute("INSERT INTO users (KEY, password, gender, state, birth_year) VALUES ('user2', 'ch@ngem3b', 'm', 'CA', 1971);")
        cursor.execute("INSERT INTO users (KEY, password, gender, state, birth_year) VALUES ('user3', 'ch@ngem3c', 'f', 'FL', 1978);")
        cursor.execute("INSERT INTO users (KEY, password, gender, state, birth_year) VALUES ('user4', 'ch@ngem3d', 'm', 'TX', 1974);")


    @since('3.0')
    def test_index_query(self):
        cursor = self.carl_prepare()

        # insert data
        cursor.execute("INSERT INTO users (KEY, password, gender, state, birth_year) VALUES ('user1', 'ch@ngem3a', 'f', 'TX', 1968);")
        cursor.execute("INSERT INTO users (KEY, password, gender, state, birth_year) VALUES ('user2', 'ch@ngem3b', 'm', 'CA', 1971);")
        cursor.execute("INSERT INTO users (KEY, password, gender, state, birth_year) VALUES ('user3', 'ch@ngem3c', 'f', 'FL', 1978);")
        cursor.execute("INSERT INTO users (KEY, password, gender, state, birth_year) VALUES ('user4', 'ch@ngem3d', 'm', 'TX', 1974);")

        result = cursor.execute("SELECT * FROM users;")
        assert len(result) == 4, "Expecting 4 users, got" + str(result)
        result = cursor.execute("SELECT state, password, session_token FROM users WHERE state='TX';")
        assert len(result) == 2, "Expecting 2 users, got" + str(result)
        result = cursor.execute("SELECT state, password, session_token FROM users WHERE state='CA';")
        assert len(result) == 1, "Expecting 1 users, got" + str(result)
        result = cursor.execute("SELECT state, password, session_token FROM users WHERE state='MA';")
        assert len(result) == 0, "Expecting 0 users, got" + str(result)


    @since('3.0')
    def test_index_prepared_statement(self):
        cursor = self.carl_prepare()

        insertPrepared = cursor.prepare("INSERT INTO users (KEY, password, gender, state, birth_year) VALUES (?, ?, ?, ?, ?);")
        selectPrepared = cursor.prepare("SELECT state, password, session_token FROM users WHERE state=?;")

        # insert data
        cursor.execute(insertPrepared.bind(('user1', 'ch@ngem3a', 'f', 'TX', 1968)))
        cursor.execute(insertPrepared.bind(('user2', 'ch@ngem3b', 'm', 'CA', 1971)))
        cursor.execute(insertPrepared.bind(('user3', 'ch@ngem3c', 'f', 'FL', 1978)))
        cursor.execute(insertPrepared.bind(('user4', 'ch@ngem3d', 'm', 'TX', 1974)))

        result = cursor.execute("SELECT * FROM users;")
        assert len(result) == 4, "Expecting 4 users, got" + str(result)
        result = cursor.execute(selectPrepared.bind(['TX']))
        assert len(result) == 2, "Expecting 2 users, got" + str(result)
        result = cursor.execute(selectPrepared.bind(['FL']))
        assert len(result) == 1, "Expecting 1 users, got" + str(result)
        result = cursor.execute(selectPrepared.bind(['MA']))
        assert len(result) == 0, "Expecting 0 users, got" + str(result)

    @since('3.0')
    def test_drop_index(self):
        cursor = self.carl_prepare()

        result = cursor.execute("SELECT * FROM system.schema_globalindexes WHERE keyspace_name='ks' AND columnfamily_name='users'")
        assert len(result) == 1, "Expecting 1 global index, got" + str(result)

        cursor.execute("DROP GLOBAL INDEX ks.users_state_idx")

        result = cursor.execute("SELECT * FROM system.schema_globalindexes WHERE keyspace_name='ks' AND columnfamily_name='users'")
        assert len(result) == 0, "Expecting 0 global indexes, got" + str(result)

    @since('3.0')
    def test_drop_indexed_column(self):
        cursor = self.carl_prepare()

        assert_invalid(cursor, "ALTER TABLE ks.users DROP state")
        assert_invalid(cursor, "ALTER TABLE ks.users ALTER state TYPE blob")

    @since('3.0')
    def test_double_indexing_column(self):
        cursor = self.carl_prepare()

        assert_invalid(cursor, "CREATE INDEX ON ks.users (state)")
        assert_invalid(cursor, "CREATE GLOBAL INDEX ON ks.users (state) DENORMALIZED (password)")

        cursor.execute("CREATE INDEX ON ks.users (gender)")
        assert_invalid(cursor, "CREATE GLOBAL INDEX ON ks.users (gender) DENORMALIZED (birth_year)")

    @since('3.0')
    def test_drop_indexed_table(self):
        cursor = self.carl_prepare()

        result = cursor.execute("SELECT * FROM system.schema_globalindexes WHERE keyspace_name='ks' AND columnfamily_name='users'")
        assert len(result) == 1, "Expecting 1 global index, got" + str(result)

        cursor.execute("DROP TABLE ks.users")

        result = cursor.execute("SELECT * FROM system.schema_globalindexes WHERE keyspace_name='ks' AND columnfamily_name='users'")
        assert len(result) == 0, "Expecting 0 global indexes, got" + str(result)
