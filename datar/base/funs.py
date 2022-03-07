"""Some functions from R-base

If a function uses DataFrame/TibbleGrouped as first argument, it may be
registered by `register_verb` and should be placed in `./verbs.py`
"""
import itertools

import numpy as np
import pandas
from pandas.api.types import is_scalar
from pipda import register_func

from ..core.middlewares import WithDataEnv
from ..core.contexts import Context
from ..core.tibble import Tibble
from ..core.utils import arg_match, name_of
from ..core.names import repair_names


@register_func(None, context=Context.EVAL)
def cut(
    x,
    breaks,
    labels=None,
    include_lowest=False,
    right=True,
    precision=2,
    ordered_result=False,
):
    """Divides the range of x into intervals and codes the values in x
    according to which interval they fall. The leftmost interval corresponds
    to level one, the next leftmost to level two and so on.

    Args:
        x: a numeric vector which is to be converted to a factor by cutting.
        breaks: either a numeric vector of two or more unique cut points or
            a single number (greater than or equal to 2) giving the number of
            intervals into which x is to be cut.
        labels: labels for the levels of the resulting category. By default,
            labels are constructed using "(a,b]" interval notation.
            If labels = False, simple integer codes are returned instead
            of a factor.
        include_lowest: bool, indicating if an ‘x[i]` equal to the lowest
            (or highest, for right = FALSE) ‘breaks’ value should be included.
        right: bool, indicating if the intervals should be closed on the right
            (and open on the left) or vice versa.
        precision:integer which is used when labels are not given. It determines
            the precision used in formatting the break numbers. Note, this
            argument is different from R's API, which is dig.lab.
        ordered_result: bool, should the result be an ordered categorical?

    Returns:
        A categorical object with the cuts
    """
    if labels is None:
        ordered_result = True

    return pandas.cut(
        x,
        breaks,
        labels=labels,
        include_lowest=include_lowest,
        right=right,
        precision=precision,
        ordered=ordered_result,
    )


@register_func(None, context=Context.EVAL)
def identity(x):
    """Return whatever passed in

    Expression objects are evaluated using parent context
    """
    return x


@register_func(None, context=Context.EVAL)
def expandgrid(*args, **kwargs):
    """Expand all combinations into a dataframe. R's `expand.grid()`"""
    iters = {}
    for arg in args:
        name = name_of(arg) or str(arg)
        iters[name] = arg
    iters.update(kwargs)

    return Tibble(
        list(itertools.product(*iters.values())),
        columns=iters.keys(),
    )


@register_func(None, context=Context.EVAL)
def outer(x, y, fun="*"):
    """Compute the outer product of two vectors.

    Args:
        x: The first vector
        y: The second vector
        fun: The function to handle how the result of the elements from
            the first and second vectors should be computed.
            The function has to be vectorized at the second argument, and
            return the same shape as y.

    Returns:
        The data frame of the outer product of x and y
    """
    if fun == "*":
        return Tibble(np.outer(x, y))

    return Tibble([fun(xelem, y) for xelem in x])


@register_func(None, context=Context.EVAL)
def make_names(names, unique=False):
    """Make names available as columns and can be accessed by `df.<name>`

    The names will be transformed using `python-slugify` with
    `lowercase=False` and `separator="_"`. When the first character is
    a digit, preface it with "_".

    If `unique` is True, the results will be fed into
    `datar.core.names.repair_names(names, "unique")`

    Args:
        names: The names
            if it is scalar, will make it into a list.
            Then all elements will be converted into strings
        unique: Whether to make the names unique

    Returns:
        Converted names
    """
    from slugify import slugify
    from . import as_character

    if is_scalar(names):
        names = [names]
    names = as_character(names)
    names = [slugify(name, separator="_", lowercase=False) for name in names]
    names = [f"_{name}" if name[0].isdigit() else name for name in names]
    if unique:
        return repair_names(names, "unique")
    return names


@register_func(None, context=Context.EVAL)
def make_unique(names):
    """Make the names unique.

    It's a shortcut for `make_names(names, unique=True)`

    Args:
        names: The names
            if it is scalar, will make it into a list.
            Then all elements will be converted into strings

    Returns:
        Converted names
    """
    return make_names(names, unique=True)


@register_func(None, context=Context.EVAL)
def rank(
    x,
    na_last=True,
    ties_method="average",
):
    """Returns the sample ranks of the values in a vector.

    Args:
        x: A numeric vector
        na_last: for controlling the treatment of `NA`s.  If `True`, missing
            values in the data are put last; if `False`, they are put
            first; if `"keep"` they are kept  with rank `NA`.
        ties_method: a character string specifying how ties are treated
            One of `average`, `first`, `dense`, `max`, and `min`
            Note that the ties_method candidates are different than the ones
            from R, because we are using `pandas.Series.rank()`. See
            https://pandas.pydata.org/docs/reference/api/pandas.Series.rank.html

    Returns:
        A numeric rank vector of the same length as `x`
    """
    ties_method = arg_match(
        ties_method,
        "ties_method",
        ["average", "first", "dense", "max", "min"],
    )

    from ..dplyr.rank import _rank

    return _rank(x, na_last, method=ties_method)


# ---------------------------------
# Plain functions
# ---------------------------------


def data_context(data):
    """Evaluate verbs, functions in the
    possibly modifying (a copy of) the original data.

    It mimic the `with` function in R, but you have to write it in a python way,
    which is using the `with` statement. And you have to use it with `as`, since
    we need the value returned by `__enter__`.

    Args:
        data: The data
        func: A function that is registered by
            `pipda.register_verb` or `pipda.register_func`.
        *args: Arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        The original or modified data
    """
    return WithDataEnv(data)