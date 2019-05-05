# pyhapool

A handy, customizable python library that provides high availability(including failover etc.) for multiple node connections.

## QuickStart

For example, we need to connect to multiple kubernetes apiserver.
```python
from pyhapool import HAEndpointPool
from kubernetes.client import ApiClient

# got configuration list which contain multiple apiservers
configuration_list = [...]
ha_pool = HAEndpointPool.from_list(configuration_list)


class HAApiClient(ApiClient):

    def call_api(self, *args, **kwargs):
        while ha_pool.data:
            with ha_pool.get_endpoint() as configuration:
                self.configuration = configuration
                return super().call_api(*args, **kwargs)
```

If any apiserver became unavailable (may raise some exceptions), `ha_pool` would switch to next endpoint until any available one been chosen(work like upstream in `nginx`).

----

more documentation is coming.
