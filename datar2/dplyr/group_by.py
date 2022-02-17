"""Group by verbs and functions
See source https://github.com/tidyverse/dplyr/blob/master/R/group-by.r
"""

from typing import Any, Union

from pandas import DataFrame
from pipda import register_verb

from ..core.exceptions import NameNonUniqueError
from ..core.tibble import Tibble, TibbleGroupby, TibbleRowwise
from ..core.contexts import Context
from ..core.utils import (
    regcall,
    vars_select,
)
from ..base import setdiff, union
from ..tibble import as_tibble

from .group_data import group_vars


@register_verb(DataFrame, context=Context.PENDING)
def group_by(
    _data: DataFrame,
    *args: Any,
    _add: bool = False,  # not working, since _data is not grouped
    _drop: bool = None,
    _sort: bool = False,
    _dropna: bool = False,
    **kwargs: Any,
) -> TibbleGroupby:
    """Takes an existing tbl and converts it into a grouped tbl where
    operations are performed "by group"

    See https://dplyr.tidyverse.org/reference/group_by.html and
    https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.groupby.html

    Args:
        _data: The dataframe
        _add: When False, the default, `group_by()` will override
            existing groups. To add to the existing groups, use `_add=True`.
        _drop: Drop groups formed by factor levels that don't appear in the
            data? The default is True except when `_data` has been previously
            grouped with `_drop=False`.
        sort_: Sort group keys.
        dropna_: If True, and if group keys contain NA values, NA values
            together with row/column will be dropped. If False, NA values
            will also be treated as the key in groups.
        *args: variables or computations to group by.
        **kwargs: Extra variables to group the dataframe

    Return:
        A `DataFrameGroupBy` object
    """
    from .mutate import mutate

    _data = regcall(mutate, _data, *args, **kwargs)

    if _drop is None:
        _drop = group_by_drop_default(_data)
    new_cols = _data._datar_meta["mutated_cols"]
    return _data.group_by(new_cols, drop=_drop, sort=_sort, dropna=_dropna)


@group_by.register(TibbleGroupby, context=Context.PENDING)
def _(
    _data: TibbleGroupby,
    *args: Any,
    _add: bool = False,
    _drop: bool = None,
    _sort: bool = False,
    _dropna: bool = False,
    **kwargs: Any,
) -> TibbleGroupby:
    """Group a grouped data frame"""
    from .mutate import mutate

    _data = regcall(mutate, _data, *args, **kwargs)
    new_cols = _data._datar_meta["mutated_cols"]
    gvars = regcall(
        union,
        regcall(group_vars, _data),
        new_cols,
    ) if _add else new_cols

    return regcall(
        group_by,
        Tibble(_data),
        *gvars,
        _drop=_drop,
        _sort_=_sort,
        _dropna_=_dropna,
    )


@register_verb(DataFrame, context=Context.SELECT)
def rowwise(
    _data: DataFrame,
    *cols: Union[str, int],
) -> TibbleRowwise:
    """Compute on a data frame a row-at-a-time

    See https://dplyr.tidyverse.org/reference/rowwise.html

    Args:
        _data: The dataframe
        *cols:  Variables to be preserved when calling summarise().
            This is typically a set of variables whose combination
            uniquely identify each row.
        base0_: Whether indexes are 0-based if columns are selected by indexes.
            If not given, will use `datar.base.get_option('index.base.0')`

    Returns:
        A row-wise data frame
    """
    if not _data.columns.is_unique:
        raise NameNonUniqueError()
    idxes = vars_select(_data.columns, *cols)
    gvars = _data.columns[idxes]
    return as_tibble(_data).rowwise(gvars)


@rowwise.register(TibbleGroupby, context=Context.SELECT)
def _(
    _data: TibbleGroupby,
    *cols: Union[str, int],
) -> TibbleRowwise:
    # grouped dataframe's columns are unique already
    if cols:
        raise ValueError(
            "Can't re-group when creating rowwise data. "
            "Either first `ungroup()` or call `rowwise()` without arguments."
        )

    return regcall(rowwise, _data, *cols)


@rowwise.register(TibbleRowwise, context=Context.SELECT)
def _(_data: TibbleRowwise, *cols: Union[str, int]) -> TibbleRowwise:
    idxes = vars_select(_data.columns, *cols)
    gvars = _data.columns[idxes]
    return _data.rowwise(gvars)


@register_verb(DataFrame, context=Context.SELECT)
def ungroup(
    x: DataFrame,
    *cols: Union[str, int],
) -> DataFrame:
    """Ungroup a grouped data

    See https://dplyr.tidyverse.org/reference/group_by.html

    Args:
        x: The data frame
        *cols: Variables to remove from the grouping variables.
        base0_: If columns are selected with indexes, whether they are 0-based.
            If not given, will use `datar.base.get_option('index.base.0')`

    Returns:
        A data frame with selected columns removed from the grouping variables.
    """
    if cols:
        raise ValueError("`*cols` is not empty.")
    return x


@ungroup.register(TibbleGroupby, context=Context.SELECT)
def _(
    x: TibbleGroupby,
    *cols: Union[str, int],
) -> Union[Tibble, TibbleGroupby]:
    obj = x._datar_meta["_grouped"].obj
    if not cols:
        return Tibble(obj)

    old_groups = regcall(group_vars, x)
    to_remove = vars_select(obj.columns, *cols)
    new_groups = regcall(
        setdiff,
        old_groups,
        obj.columns[to_remove],
    )

    return regcall(group_by, obj, *new_groups)


@ungroup.register(TibbleRowwise, context=Context.SELECT)
def _(
    x: TibbleRowwise,
    *cols: Union[str, int],
) -> DataFrame:
    if cols:
        raise ValueError("`*cols` is not empty.")
    return Tibble(x)


def group_by_drop_default(_tbl: DataFrame) -> bool:
    """Get the groupby _drop attribute of dataframe"""
    grouped = getattr(_tbl, "_datar_meta", {}).get("_grouped", None)
    if not grouped:
        return True
    return grouped.observed
