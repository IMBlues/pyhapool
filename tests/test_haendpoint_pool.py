import unittest

from blue_krill.connection_tools.ha_endpoints_pool import HAEndpointsPool, Endpoint
from blue_krill.connection_tools.ha_algorithm import BasicHAAlgorithm


class TestFailOver(unittest.TestCase):

    def setUp(self) -> None:
        fake_list = [f"fake{x}" for x in range(5)]
        self.pool = HAEndpointsPool.from_list(fake_list)

    def test_fail(self):
        self.pool.fail()

        fake_one_score = self.pool.active.score
        assert self.pool.active.failure_count == 1

        self.pool.elect()
        assert fake_one_score < self.pool.active.score

    def test_fail_custom_score_delta(self):
        self.pool.fail(score_delta=10)
        assert self.pool.active.score == 90

    def test_success(self):
        self.pool.succeed()

        assert self.pool.active.success_count == 1
        assert self.pool.active.score == 101

        self.pool.succeed(score_delta=10)
        assert self.pool.active.score == 111

    def test_isolate(self):
        for i in range(self.pool.algorithm.failure_threshold):
            self.pool.fail()

        assert len(self.pool.data) == 4

    def test_get_endpoint(self):
        with self.pool.get_endpoint(auto_reelect=False) as fake_item:
            # use fake item to do something
            raise ValueError("单元测试专属错误")

        assert self.pool.active.failure_count == 1

        self.pool.elect()
        with self.pool.get_endpoint(auto_reelect=False) as fake_item:
            # nothing happen
            pass

        assert self.pool.active.failure_count == 0
        assert self.pool.active.success_count == 1

    def test_get_endpoint_auto_reelect(self):
        with self.pool.get_endpoint() as fake_item:
            # use fake item to do something
            raise ValueError("单元测试专属错误")

        assert self.pool.active.failure_count == 0

    def test_custom_isolate(self):
        def custom_isolate(endpoint):
            return endpoint.failure_count > 0

        self.pool.fail(isolate_method=custom_isolate)

        assert len(self.pool.data) == 4

    def test_custom_elect(self):
        def custom_isolate(endpoints):
            return endpoints[0]

        self.pool.elect(method=custom_isolate)

        # 此时 fake0 已经得分偏低
        self.pool.fail()
        self.pool.fail()

        assert self.pool.active.raw == "fake0"


class TestBasicHAAlgorithm(unittest.TestCase):

    def setUp(self) -> None:
        self.algo = BasicHAAlgorithm()

        fake_list = [f"fake{x}" for x in range(5)]
        self.endpoints = [Endpoint(raw=x) for x in fake_list]

    def test_find_tops(self):
        with self.assertRaises(ValueError):
            self.algo.elect([])

        self.endpoints[0].succeed(10)
        self.endpoints[1].succeed(20)
        self.endpoints[2].succeed(20)

        tops = self.algo._find_tops(self.endpoints)
        assert len(tops) == 2
        assert tops[0].score == 120


if __name__ == "__main__":
    unittest.main()
