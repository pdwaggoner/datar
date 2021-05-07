## Import submodule, verbs and functions from datar

You can import everything (all verbs and functions) from datar by:
```python
from datar.all import *
```

which is not recommended. Instead, you can import individual verbs or functions by:
```python
from datar.all import mutate
```

!!! Attention

    When you use `from datar.all import *`, you need to pay attention to the python builtin names that are covered by `datar`. For example, `slice` will be `datar.dplyr.slice` instead of `builtins.slice`. To refer to the builtin one, you need to:
    ```python
    import builtins

    s = builtins.slice(None, 3, None) # [:3]
    ```

Or if you know the origin of the verb, you can also do:
```python
from datar.dplyr import mutate
```

You can also keep the namespace:
```python
from datar import dplyr

# df = tibble(x=1)
# then use it with the dplyr namespace:
df >> dplyr.mutate(y=2)
```

## Import datasets from datar

Note that `from datar.all import *` will not import datasets

!!! note

    Dataset has to be imported individually. So that `from datar.datasets import *` won't work.

You don't have to worry about other datasets to be imported and take up the memory when you import one. The dataset is only loaded into memory when you explictly import it individually.

See also [datasets](../datasets) for details about available datasets.