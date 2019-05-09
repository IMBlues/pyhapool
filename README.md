# pyhapool 🐸

A handy, customizable python library that provides high availability(including failover etc.) for multiple node connections.

## Install

```bash
pip install hapool
```

## QuickStart

You can use the `get_endpoint()` directly
```python
from hapool import HAEndpointPool

endpoint_raw_list = [...]
ha_pool = HAEndpointPool.from_list(endpoint_raw_list)

with ha_pool.get_endpoint() as endpoint:
    # put your own logic here
    pass
```

Or manually call APIs to embed it into your own logic.
```python
from hapool import HAEndpointPool

endpoint_raw_list = [...]
ha_pool = HAEndpointPool.from_list(endpoint_raw_list)

endpoint_raw = ha_pool.pick()

# mark the endpoint as failure
ha_pool.fail()

# mark the endpoint as success
ha_pool.succeed()

# elect a new endpoint
ha_pool.elect()
new_endpoint = ha_pool.active
# or you could re-pick raw item directly
new_endpoint_raw = ha_pool.pick()

# If there are multiple failures of the endpoint that trigger the isolation, 
# then we can manually call the `recover()` to try to recover it.
ha_pool.recover()
```

All the above interfaces have been integrated in `get_endpoint`, so it is recommended to use `get_endpoint` directly.

## Customization
`hapool` provides two methods for customizing policies.

### use standalone methods
```python
from typing import List
from hapool import Endpoint

# if we don't want to isolate any endpoint
def never_isolate(endpoint: Endpoint) -> bool:
    return False

ha_pool.fail(isolate_method=never_isolate)

# always get first item
def first_first(endpoints: List[Endpoint]) -> Endpoint:
    return endpoints[0]

first_endpoint = ha_pool.pick(elect_method=first_first)

# any success leads to recovery
def success_to_recover(endpoint: Endpoint) -> bool:
    return endpoint.success_count > 0
    
ha_pool.recover(method=success_to_recover)
```

### use BasicHAAlgorithm class

If you have a complete strategy, please use `BasicHAAlgorithm`.

```python
from hapool import BasicHAAlgorithm, HAEndpointPool

class AwesomeAlgorithm(BasicHAAlgorithm):

    def find_best_endpoint(self, endpoints: List['Endpoint']) -> 'Endpoint':
        # always get first item
        return endpoints[0]

    def should_be_isolated(self, endpoint: 'Endpoint') -> bool:
        # if we don't want to isolate any endpoint
        return False

    def should_be_recovered(self, endpoint: 'Endpoint') -> bool:
        # any success leads to recovery
        return endpoint.success_count > 0
        
endpoint_raw_list = [...]
ha_pool = HAEndpointPool.from_list(endpoint_raw_list)
ha_pool.algorithm = AwesomeAlgorithm()

# use ha_pool as usual
with ha_pool.get_endpoint() as endpoint:
    pass
```

## Examples

### connect to kubernetes
For example, We may need to connect to a kubernetes cluster with multiple apiserver endpoints.

```python
from hapool import HAEndpointPool
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
