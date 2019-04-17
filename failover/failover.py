# -*- coding: utf-8 -*-
"""
对于一般的 failOver 而言，我们会关注两个个指标：
- 失败目标的惩罚力度，可以简单理解为错误多少次我们将隔离目标
- 已经隔离目标的故障恢复能力，即多长时间或者多少次访问取消隔离

同时我们需要关注几个变量：
- 错误的范围，是网络层，协议层，还是应用层
- 隔离取消的条件，是否由独立的健康探测逻辑

暂时留空
"""
import logging
import random
from datetime import datetime
from threading import RLock
from contextlib import contextmanager
from typing import TypeVar, Any, List, NoReturn, Optional, Callable, Type
from dataclasses import dataclass, field

from .exceptions import NoEndPointAvailable

logger = logging.getLogger(__name__)

TFailOverPool = TypeVar('TFailOverPool', bound='FailOverPool')


@dataclass
class FailOverPool:
    """FailOver pool"""
    # 同一块内存读写，保证线程安全
    _rlock = RLock()

    _active: Optional['EndPoint'] = None
    # 包含所有 endpoint
    _all_pool: List['EndPoint'] = field(default_factory=list)
    # 只包含当前可用的 endpoint
    _pool: List['EndPoint'] = field(default_factory=list)

    # 默认失败3次剔除
    failure_threshold: int = 3
    success_weight: int = 1
    failure_weight: int = -50

    def __len__(self):
        return len(self._pool)

    @classmethod
    def from_list(cls, raw_list: List) -> TFailOverPool:
        """从列表中直接获得"""
        pool = cls()
        if not raw_list:
            raise ValueError("raw list can not be empty")

        for raw_end_point in raw_list:
            pool.add(raw_end_point)
        return pool

    @property
    def data(self) -> List:
        return self._pool

    @property
    def active(self) -> 'EndPoint':
        return self._active

    def add(self, raw_end_point: Any) -> NoReturn:
        """接收任意类型，挂载到 endpoint 上"""
        self._all_pool.append(EndPoint(raw=raw_end_point))
        self._pool.append(EndPoint(raw=raw_end_point))

    def fail(self, isolate_method: Callable[['EndPoint'], bool] = None, weight: int = None) -> NoReturn:
        """为当前 active"""
        if not self._active:
            self.elect()

        if not weight:
            weight = self.failure_weight

        with self._rlock:
            self._active.fail(weight=weight)
            # 只有失败时才扫描当前节点可用性
            self.scan(isolate_method)

    def succeed(self) -> NoReturn:
        if not self._active:
            self.elect()

        with self._rlock:
            self._active.succeed(weight=self.success_weight)

    def scan(self, method: Callable[['EndPoint'], bool] = None) -> NoReturn:
        if not method:
            method = self.default_isolate_method

        with self._rlock:
            pool_copy = [x for x in self._pool]
            for ep in pool_copy:
                if method(ep):
                    # 从可用列表中剔除
                    self._pool.remove(ep)

        if not self._pool:
            raise NoEndPointAvailable("no Endpoint available in pool")

    def recovery(self):
        """实现一段时间能够把删除的 endpoint 加回到 _pool"""
        raise NotImplementedError

    def elect(self, method: Callable[[List['EndPoint']], 'EndPoint'] = None) -> 'Any':
        if not self._pool:
            raise NoEndPointAvailable("no EndPoint available in pool")

        if not method:
            method = self.default_elect_method
        elected = method(self._pool)

        with self._rlock:
            self._active = elected
            logger.info(f"elect {elected.raw} as new active endpoint with weight<{elected._weight}>")
            return self._active.raw

    @staticmethod
    def _find_tops(endpoints: List['EndPoint']) -> List['EndPoint']:
        """
        Q: 为什么不用 heapq.nlargest?
        A: 因为我们需要找到最大的一类，而不是一个

        例如: [50, 50, 100, 100, 100] 得到的应该是 [100, 100, 100]
        """
        tops = []
        for ep in endpoints:
            if not tops:
                tops.append(ep)
                continue

            if ep > tops[0]:
                tops.clear()
                tops.append(ep)
                continue
            elif ep == tops[0]:
                tops.append(ep)
                continue
        return tops

    def default_elect_method(self, endpoints: List['EndPoint']) -> 'EndPoint':
        """默认使用权重排序+随机选出可用"""
        return random.choice(self._find_tops(endpoints))

    def default_isolate_method(self, endpoint: 'EndPoint') -> bool:
        """默认按照错误次数剔除"""
        return endpoint.failure_count >= self.failure_threshold

    @contextmanager
    def get_endpoint(self,
                     auto_reelect: bool = True,
                     isolate_method: Callable[['EndPoint'], bool] = None,
                     elect_method: Callable[[List['EndPoint']], 'EndPoint'] = None,
                     exempt_exceptions: List[Type[Exception]] = None) -> Any:
        """上下文管理器封装整个流程"""
        try:
            if not self._active:
                self.elect()

            yield self._active.raw
        except Exception as e:
            if exempt_exceptions:
                for exempt_exception in exempt_exceptions:
                    if isinstance(e, exempt_exception):
                        logger.info(f"fail over pool got exception: {e}, "
                                    f"but raising anyway according to upper caller")
                        raise

            logger.warning(f"fail over pool got exception: {e}, "
                           f"the active endpoint {self._active} will be mark as failure")
            self.fail(isolate_method)
            if auto_reelect:
                self.elect(elect_method)
        else:
            self.succeed()


@dataclass(order=True)
class EndPoint:
    raw: Any = field(compare=False)
    _weight: int = 100
    success_count: int = 0
    failure_count: int = 0
    # 为 recovery 逻辑预留
    last_failure: datetime = None

    def __repr__(self):
        return repr(self.raw) + f"-weigth<{self._weight}>"

    def __hash__(self):
        return hash(repr(self))

    def fail(self, weight: int = 0) -> NoReturn:
        self.last_failure = datetime.now()
        self.failure_count += 1
        self._weight += weight

    def succeed(self, weight: int = 0) -> NoReturn:
        self.success_count += 1
        self._weight += weight
