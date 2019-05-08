# pyhapool

A handy, customizable python library that provides high availability(including failover etc.) for multiple node connections.

## Install

```bash
pip install hapool
```

## QuickStart

For example, We may need to connect to a kubernetes cluster with multiple apiserver endpoints.

```python
from pyhapool import HAEndpointPool
from kubernetes.client import ApiClient

# got configuration list which contains apiservers' configurations
configuration_list = [...]
ha_pool = HAEndpointPool.from_list(configuration_list)


class HAApiClient(ApiClient):

    def call_api(self, *args, **kwargs):
        while ha_pool.data:
            with ha_pool.get_endpoint() as configuration:
                self.configuration = configuration
                return super().call_api(*args, **kwargs)
```

For any request, if the current apiserver endpoint becomes unavailable, ha_pool will automatically switch to the next available endpoint until the request is completed normally.
