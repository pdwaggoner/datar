import builtins
from itertools import chain
import numpy
import pandas

from pandas.core.groupby.generic import SeriesGroupBy
from pipda.context import ContextSelect
from plyrda.contexts import ContextEvalWithUsedRefs, ContextSelectSlice
import sys
from pandas.core.groupby.groupby import GroupBy
from pandas.core.indexes.multi import MultiIndex
from pandas.core.groupby import DataFrameGroupBy
from pandas.core.series import Series
from pipda.utils import Expression, evaluate_args, evaluate_expr
from typing import Any, Callable, Iterable, List, Mapping, Optional, Union
from pandas import DataFrame
from pipda import register_verb, Context

from .utils import IterableLiterals, align_value, expand_slice, get_n_from_prop, list_intersect, objectize, copy_df, df_assign_item, list_diff, list_union, select_columns, to_df
from .middlewares import Across, CAcross, Collection, DescSeries, IfCross, Negated, RowwiseDataFrame, Inverted
from .exceptions import ColumnNameInvalidError

@register_verb(DataFrame)
def head(_data, n: int = 5) -> DataFrame:
    """Get the first n rows of the dataframe

    Args:
        n: The number of rows to return

    Returns:
        The dataframe with first N rows
    """
    return _data.head(n)

@head.register(DataFrameGroupBy)
def _(_data: DataFrameGroupBy, n: int = 5) -> DataFrame:
    return _data.obj.head(n)

@register_verb(DataFrame)
def tail(_data, n=5):
    """Get the last n rows of the dataframe

    Args:
        n: The number of rows to return

    Returns:
        The dataframe with last N rows
    """
    return _data.tail(n)

@tail.register(DataFrameGroupBy)
def _(_data: DataFrameGroupBy, n: int = 5) -> DataFrame:
    return _data.obj.tail(n)

@register_verb((DataFrame, DataFrameGroupBy))
def select(
        _data: DataFrame,
        *columns: Union[str, Iterable[str], Inverted],
        **renamings: Mapping[str, str]
) -> DataFrame:
    """Select (and optionally rename) variables in a data frame

    Args:
        *columns: The columns to select
        **renamings: The columns to rename and select in new => old column way.

    Returns:
        The dataframe with select columns
    """
    selected = select_columns(
        _data.columns,
        *columns,
        *renamings.values()
    )
    # old -> new
    new_names = {val: key for key, val in renamings.items() if val in selected}
    if new_names:
        return _data[selected].rename(columns=new_names)
    return _data[selected]

@register_verb((DataFrame, DataFrameGroupBy), context=None)
def transmutate(
        _data: DataFrame,
        *acrosses: Across,
        _keep: str = 'all',
        _before: Optional[str] = None,
        _after: Optional[str] = None,
        **kwargs: Any
) -> DataFrame:
    return mutate(
        _data,
        *acrosses,
        _keep='none',
        _before=_before,
        _after=_after,
        **kwargs
    )

@register_verb(DataFrame, context=Context.SELECT)
def pivot_longer(
        _data,
        cols,
        names_to="name",
        names_prefix=None,
        names_sep=None,
        names_pattern=None,
        names_ptypes=None,
        names_transform=None,
        # names_repair="check_unique",
        values_to="value",
        values_drop_na=False,
        values_ptypes=None,
        values_transform=None
):
    columns = select_columns(_data.columns, cols)
    id_columns = list_diff(_data.columns, columns)
    var_name = '__tmp_names_to__' if names_pattern or names_sep else names_to
    ret = _data.melt(
        id_vars=id_columns,
        value_vars=columns,
        var_name=var_name,
        value_name=values_to,
    )

    if names_pattern:
        ret[names_to] = ret['__tmp_names_to__'].str.extract(names_pattern)
        ret.drop(['__tmp_names_to__'], axis=1, inplace=True)

    if names_prefix:
        ret[names_to] = ret[names_to].str.replace(names_prefix, '')

    if '.value' in names_to:
        ret2 = ret.pivot(columns='.value', values=values_to)
        rest_columns = list_diff(ret.columns, ['.value', values_to])
        ret2.loc[:, rest_columns] = ret.loc[:, rest_columns]

        ret2_1 = ret2.iloc[:(ret2.shape[0] // 2), ]
        ret2_2 = ret2.iloc[(ret2.shape[0] // 2):, ].reset_index()
        ret = ret2_1.assign(**{col: ret2_2[col] for col in ret2_1.columns
                               if ret2_1[col].isna().all()})

    if values_drop_na:
        ret.dropna(subset=[values_to], inplace=True)
    if names_ptypes:
        for key, ptype in names_ptypes.items():
            ret[key] = ret[key].astype(ptype)
    if values_ptypes:
        for key, ptype in values_ptypes.items():
            ret[key] = ret[key].astype(ptype)
    if names_transform:
        for key, tform in names_transform.items():
            ret[key] = ret[key].apply(tform)
    if values_transform:
        for key, tform in values_transform.items():
            ret[key] = ret[key].apply(tform)

    return ret


@register_verb(DataFrame, context=None)
def group_by(
        _data: DataFrame,
        *columns: str,
        _add: bool = False, # not working, since _data is not grouped
        **kwargs: Any
) -> DataFrameGroupBy:
    if kwargs:
        _data = mutate(_data, **kwargs)

    columns = evaluate_args(columns, _data, Context.SELECT)
    columns = select_columns(_data.columns, *columns, *kwargs.keys())
    # requires pandas 1.2+
    # eariler versions have bugs with apply/transform
    # GH35889
    return _data.groupby(columns, dropna=False)

@group_by.register(DataFrameGroupBy)
def _(
    _data: DataFrameGroupBy,
    *columns: str,
    _add: bool = False,
    **kwargs: Any
) -> DataFrameGroupBy:
    if kwargs:
        _data = mutate(_data, **kwargs)

    columns = evaluate_args(columns, _data, Context.SELECT)
    columns = select_columns(_data.obj.columns, *columns, *kwargs.keys())
    if _add:
        groups = Collection(*_data.grouper.names) + columns
        return _data.obj.groupby(groups, dropna=False)
    return _data.obj.groupby(columns, dropna=False)

@register_verb(DataFrameGroupBy)
def ungroup(_data: DataFrameGroupBy) -> DataFrame:
    return _data.obj

@register_verb(DataFrameGroupBy)
def group_vars(_data: DataFrameGroupBy) -> List[str]:
    return _data.grouper.names

group_cols = group_vars

@register_verb(DataFrameGroupBy)
def group_rows(_data: DataFrameGroupBy) -> List[str]:
    return _data.grouper.groups

@register_verb((DataFrame, DataFrameGroupBy))
def group_keys(
        _data: Union[DataFrame, DataFrameGroupBy],
        *cols: str,
        **kwargs: Any,
) -> DataFrame:
    if not isinstance(_data, DataFrameGroupBy):
        _data = group_by(_data, *cols, **kwargs)
    group_levels = list(_data.groups.keys())
    return DataFrame(group_levels, columns=_data.grouper.names)

@register_verb((DataFrame, DataFrameGroupBy), context=Context.MIXED)
def summarise(
        _data: Union[DataFrame, DataFrameGroupBy],
        *acrosses: Across,
        _groups: Optional[str] = None,
        **kwargs: Any
) -> DataFrame:
    """Summarise each group to fewer rows

    See: https://dplyr.tidyverse.org/reference/summarise.html
    """
    across = {} # no need OrderedDict in python3.7+ anymore
    for acrs in acrosses:
        across.update(
            acrs.evaluate(Context.EVAL, _data)
            if isinstance(acrs, Across)
            else acrs
        )

    across.update(kwargs)
    kwargs = across

    ret = None
    if isinstance(_data, RowwiseDataFrame) and _data.rowwise is not True:
        ret = _data.loc[:, _data.rowwise]

    for key, val in kwargs.items():
        if isinstance(val, CAcross):
            val.names = key
        if isinstance(val, Across):
            val = DataFrame(val.evaluate(Context.EVAL, _data))

        if ret is None:
            ret = to_df(val, key)
        # if isinstance(val, Series) and val.index.name == ret.index.name:
        #     # in case val has more rows than ret, ie. quantile
        #     # we expand ret
        #     ret =  ret.loc[val.index, :]
        #     ret[key] = val
        else:
            ret[key] = align_value(val, ret)

    if _groups == 'rowwise':
        return RowwiseDataFrame(ret)

    if not isinstance(_data, DataFrameGroupBy):
        return ret

    if _groups is None:
        if ret.shape[0] == 1:
            _groups = 'drop_last'
        elif isinstance(ret.index, MultiIndex):
            _groups = 'drop_last'

    ret.reset_index(inplace=True)
    group_keys = _data.grouper.names
    if _groups == 'drop_last':
        return ret.groupby(group_keys[:-1]) if group_keys[:-1] else ret

    if _groups == 'keep':
        return ret.groupby(_data.grouper) # even keep the unexisting levels

    # else:
    # todo: raise
    return ret

summarize = summarise

@register_verb(DataFrame)
def rowwise(_data: DataFrame, *columns: str) -> RowwiseDataFrame:
    columns = select_columns(_data.columns, columns)
    return RowwiseDataFrame(_data, rowwise=columns)

@rowwise.register(DataFrameGroupBy)
def _(_data: DataFrameGroupBy, *columns: str) -> RowwiseDataFrame:
    columns = select_columns(_data.obj.columns, columns)
    return RowwiseDataFrame(_data, rowwise=columns)

@register_verb((DataFrame, DataFrameGroupBy), context=Context.EVAL)
def filter(
        _data: DataFrame,
        condition,
        *conditions,
        _preserve=False
):
    if isinstance(condition, IfCross):
        condition = condition.evaluate(Context.EVAL, _data)

    # check condition, conditions
    for cond in conditions:
        if isinstance(cond, IfCross):
            cond = cond.evaluate(Context.EVAL, _data)
        condition = condition & cond
    try:
        condition = objectize(condition).values.flatten()
    except AttributeError:
        ...

    ret = objectize(_data)[condition]
    if isinstance(_data, DataFrameGroupBy):
        grouper = _data.grouper if _preserve else _data.grouper.names
        return ret.groupby(grouper, dropna=True)
    return ret

@register_verb((DataFrame, DataFrameGroupBy), context=Context.UNSET)
def debug(
        _data: Union[DataFrame, DataFrameGroupBy],
        *args: Any,
        context: Union[Context, str] = Context.SELECT,
        **kwargs: Any
) -> None: # not going any further

    def print_msg(msg: str, end: str = "\n"):
        sys.stderr.write(f"[plyrda] DEBUG: {msg}{end}")

    if isinstance(_data, DataFrameGroupBy):
        print_msg("# DataFrameGroupBy:")
        print_msg(_data.describe())
    else:
        print_msg("# DataFrame:")
        print_msg(_data)

    if args:
        for i, arg in enumerate(args):
            print_msg(f"# Arg#{i+1}")
            print_msg("## Raw")
            print_msg(arg)
            print_msg("## Evaluated")
            print_msg(evaluate_expr(arg, _data, context))

    if kwargs:
        for key, val in kwargs.items():
            print_msg(f"# Kwarg#{key}")
            print_msg("## Raw")
            print_msg(val)
            print_msg("## Evaluated")
            print_msg(evaluate_expr(val, _data, context))


@register_verb((DataFrame, DataFrameGroupBy), context=None)
def count(
        _data: Union[DataFrame, DataFrameGroupBy],
        *columns: Any,
        wt: Optional[str] = None,
        sort: bool = False,
        name: str = 'n',
        **mutates: Any
) -> DataFrame:
    """Count observations by group

    See: https://dplyr.tidyverse.org/reference/count.html
    """
    _data = objectize(_data)
    columns = evaluate_args(columns, _data, Context.SELECT)
    columns = select_columns(_data.columns, *columns)

    wt = evaluate_expr(wt, _data, Context.SELECT)
    _data = mutate(_data, **mutates)

    columns = columns + list(mutates)
    grouped = _data.groupby(columns, dropna=False)

    if not wt:
        count_frame = grouped[columns].size().to_frame(name=name)
    else:
        count_frame = grouped[wt].sum().to_frame(name=name)

    ret = count_frame.reset_index(level=columns)
    if sort:
        ret = ret.sort_values([name], ascending=[False])
    return ret


@register_verb((DataFrame, DataFrameGroupBy), context=Context.SELECT)
def tally(
        _data: Union[DataFrame, DataFrameGroupBy],
        wt: str = None,
        sort: bool = False,
        name: str = 'n'
) -> DataFrame:
    if isinstance(_data, DataFrameGroupBy):
        return count(_data, *_data.grouper.names, wt=wt, sort=sort, name=name)

    return DataFrame({
        name: [_data.shape[0] if wt is None else _data[wt].sum()]
    })

@register_verb((DataFrame, DataFrameGroupBy), context=None)
def add_count(
        _data: Union[DataFrame, DataFrameGroupBy],
        *columns: Any,
        wt: Optional[str] = None,
        sort: bool = False,
        name: str = 'n',
        **mutates: Any
) -> Union[DataFrame, DataFrameGroupBy]:
    count_frame = count(_data, *columns, wt=wt, sort=sort, name=name, **mutates)
    ret = objectize(_data).merge(
        count_frame,
        on=count_frame.columns.to_list()[:-1]
    )

    if sort:
        ret = ret.sort_values([name], ascending=[False])

    if isinstance(_data, DataFrameGroupBy):
        return ret.groupby(_data.grouper.names, dropna=False)
    return ret

@register_verb((DataFrame, DataFrameGroupBy), context=Context.SELECT)
def add_tally(
        _data: Union[DataFrame, DataFrameGroupBy],
        wt: str = None,
        sort: bool = False,
        name: str = 'n'
) -> Union[DataFrame, DataFrameGroupBy]:
    tally_frame = tally(_data, wt=wt, sort=False, name=name)

    ret = objectize(_data).assign(**{
        name: tally_frame.values.flatten()[0]
    })

    if sort:
        ret = ret.sort_values([name], ascending=[False])

    if isinstance(_data, DataFrameGroupBy):
        return ret.groupby(_data.grouper.names, dropna=False)

    return ret


@register_verb((DataFrame, DataFrameGroupBy), context=Context.MIXED)
def distinct(
        _data: Union[DataFrame, DataFrameGroupBy],
        *columns: Any,
        _keep_all: bool = False,
        **mutates: Any
) -> Union[DataFrame, DataFrameGroupBy]:

    data = objectize(_data)

    all_columns = data.columns
    columns = select_columns(all_columns, *columns)
    if isinstance(_data, DataFrameGroupBy):
        columns = list_union(_data.grouper.names, columns)

    data = mutate(data, **mutates)
    columns = columns + list(mutates)

    if not columns:
        columns = all_columns

    uniq_frame = data.drop_duplicates(columns, ignore_index=True)
    ret = uniq_frame if _keep_all else uniq_frame[columns]
    if isinstance(_data, DataFrameGroupBy):
        return ret.groupby(_data.grouper.names, dropna=False)
    return ret

@register_verb((DataFrame, DataFrameGroupBy))
def dim(_data: Union[DataFrame, DataFrameGroupBy]):
    return objectize(_data).shape

@register_verb((DataFrame, DataFrameGroupBy))
def nrow(_data: Union[DataFrame, DataFrameGroupBy]):
    return dim(_data)[0]

@register_verb((DataFrame, DataFrameGroupBy))
def ncol(_data: Union[DataFrame, DataFrameGroupBy]):
    return dim(_data)[1]

@register_verb((DataFrame, DataFrameGroupBy), context=Context.SELECT)
def pull(
        _data: Union[DataFrame, DataFrameGroupBy],
        var: Union[int, str] = -1,
        name: Optional[str] = None,
        to_list: bool = False
) -> Iterable[Any]:
    _data = objectize(_data)
    if isinstance(var, int):
        var = _data.columns[var]

    if name:
        return zip(_data[name].values, _data[var].values)

    if to_list:
        return _data[var].values.tolist()
    return _data[var].values

@register_verb(DataFrame, context=Context.SELECT)
def rename(
        _data: DataFrame,
        **kwargs: str
) -> DataFrame:

    return _data.rename(columns={val: key for key, val in kwargs.items()})


@register_verb(DataFrame, context=Context.SELECT)
def rename_with(
        _data: DataFrame,
        _fn: Callable[[str], str],
        _cols: Optional[Iterable[str]] = None
) -> DataFrame:
    _cols = _cols or _data.columns

    new_columns = {col: _fn(col) for col in _cols}
    return _data.rename(columns=new_columns)

@register_verb(DataFrame, context=ContextSelectSlice())
def slice(
        _data: DataFrame,
        rows: Any,
        _preserve: bool = False
) -> DataFrame:
    rows = expand_slice(rows, nrow(_data))
    return _data.iloc[rows, :]

# todo: slice.register(DataFrameGroupBy)

@register_verb(DataFrame)
def slice_head(
        _data: DataFrame,
        n: Optional[int] = None,
        prop: Optional[float] = None
) -> DataFrame:
    n = get_n_from_prop(nrow(_data), n, prop)
    rows = list(range(n))
    return _data.iloc[rows, :]

@slice_head.register(DataFrameGroupBy)
def _(
        _data: DataFrameGroupBy,
        n: Optional[Union[int, Iterable[int]]] = None,
        prop: Optional[Union[float, Iterable[float]]] = None
) -> DataFrame:
    # any other better way?
    total = _data.size().to_frame(name='size')
    total['n'] = n
    total['prop'] = prop
    indexes = total.apply(
        lambda row: _data.groups[row.name][
            :get_n_from_prop(row.size, row.n, row.prop)
        ],
        axis=1
    )
    indexes = numpy.concatenate(indexes.values)
    return _data.obj.iloc[indexes, :].groupby(_data.grouper, dropna=False)

@register_verb(DataFrame)
def slice_tail(
        _data: DataFrame,
        n: Optional[int] = 1,
        prop: Optional[float] = None
) -> DataFrame:
    n = get_n_from_prop(nrow(_data), n, prop)
    rows = [-(elem+1) for elem in range(n)]
    return _data.iloc[rows, :]

@slice_tail.register(DataFrameGroupBy)
def _(
        _data: DataFrameGroupBy,
        n: Optional[Union[int, Iterable[int]]] = None,
        prop: Optional[Union[float, Iterable[float]]] = None
) -> DataFrame:
    # any other better way?
    total = _data.size().to_frame(name='size')
    total['n'] = n
    total['prop'] = prop
    indexes = total.apply(
        lambda row: _data.groups[row.name][
            -get_n_from_prop(row.size, row.n, row.prop):
        ],
        axis=1
    )
    indexes = numpy.concatenate(indexes.values)
    return _data.obj.iloc[indexes, :].groupby(_data.grouper, dropna=False)

@register_verb(DataFrame, context=Context.EVAL)
def slice_min(
        _data: DataFrame,
        order_by: Series,
        n: Optional[int] = 1,
        prop: Optional[float] = None,
        with_ties: Union[bool, str] = True
) -> DataFrame:
    data = _data.assign(**{'__slice_order__': order_by.values})
    n = get_n_from_prop(nrow(_data), n, prop)

    keep = {True: 'all', False: 'first'}.get(with_ties, with_ties)
    return data.nsmallest(n, '__slice_order__', keep).drop(
        columns=['__slice_order__']
    )

# todo: slice_min.register(DataFrameGroupBy)

@register_verb(DataFrame, context=Context.EVAL)
def slice_max(
        _data: DataFrame,
        order_by: Series,
        n: Optional[int] = 1,
        prop: Optional[float] = None,
        with_ties: Union[bool, str] = True
) -> DataFrame:
    data = _data.assign(**{'__slice_order__': order_by.values})
    n = get_n_from_prop(nrow(_data), n, prop)

    keep = {True: 'all', False: 'first'}.get(with_ties, with_ties)
    return data.nlargest(n, '__slice_order__', keep).drop(
        columns=['__slice_order__']
    )

# todo: slice_max.register(DataFrameGroupBy)

@register_verb(DataFrame, context=Context.EVAL)
def slice_sample(
        _data: DataFrame,
        n: Optional[int] = 1,
        prop: Optional[float] = None,
        weight_by: Optional[Iterable[Union[int, float]]] = None,
        replace: bool = False,
        random_state: Any = None
) -> DataFrame:
    n = get_n_from_prop(nrow(_data), n, prop)

    return _data.sample(
        n=n,
        replace=replace,
        weights=weight_by,
        random_state=random_state,
        axis=0
    )

# todo: slice_sample.register(DataFrameGroupBy)

# Two table verbs
# ---------------

@register_verb(DataFrame)
def bind_rows(
        _data: DataFrame,
        *datas: DataFrame
) -> DataFrame:

    return pandas.concat([_data, *datas])

@register_verb(DataFrame)
def bind_cols(
        _data: DataFrame,
        *datas: DataFrame
) -> DataFrame:

    return pandas.concat([_data, *datas], axis=1)

@register_verb(DataFrame)
def intersect(
    _data: DataFrame,
    *datas: DataFrame,
    on: Optional[Union[str, List[str]]] = None
) -> DataFrame:
    if not on:
        on = _data.columns.to_list()

    return pandas.merge(_data, *datas, on=on, how='inner') >> distinct(*on)

@register_verb(DataFrame)
def union(
    _data: DataFrame,
    *datas: DataFrame,
    on: Optional[Union[str, List[str]]] = None
) -> DataFrame:
    if not on:
        on = _data.columns.to_list()

    return pandas.merge(_data, *datas, on=on, how='outer') >> distinct(*on)

@register_verb(DataFrame)
def setdiff(
    _data: DataFrame,
    data2: DataFrame,
    on: Optional[Union[str, List[str]]] = None
) -> DataFrame:
    if not on:
        on = _data.columns.to_list()

    return _data.merge(
        data2,
        how='outer',
        on=on,
        indicator=True
    ).loc[
        lambda x : x['_merge']=='left_only'
    ].drop(columns=['_merge']) >> distinct(*on)

@register_verb(DataFrame)
def union_all(
    _data: DataFrame,
    data2: DataFrame
) -> DataFrame:
    return bind_rows(_data, data2)

@register_verb(DataFrame)
def setequal(
    _data: DataFrame,
    data2: DataFrame
) -> DataFrame:
    data1 = _data.sort_values(by=_data.columns.to_list()).reset_index(drop=True)
    data2 = data2.sort_values(by=data2.columns.to_list()).reset_index(drop=True)
    return data1.equals(data2)

@register_verb(DataFrame)
def inner_join(
    x: DataFrame,
    y: DataFrame,
    by: Optional[Union[Iterable[str], Mapping[str, str]]] = None,
    copy: bool = False,
    suffix: Iterable[str] = ("_x", "_y"),
    keep: bool = False
) -> DataFrame:
    if isinstance(by, dict):
        right_on=list(by.values())
        ret = pandas.merge(
            x, y,
            left_on=list(by.keys()),
            right_on=right_on,
            how='inner',
            copy=copy,
            suffixes=suffix
        )
        if not keep:
            return ret.drop(columns=right_on)
        return ret
    return pandas.merge(x, y, on=by, how='inner', copy=copy, suffixes=suffix)

@register_verb(DataFrame)
def left_join(
    x: DataFrame,
    y: DataFrame,
    by: Optional[Union[Iterable[str], Mapping[str, str]]] = None,
    copy: bool = False,
    suffix: Iterable[str] = ("_x", "_y"),
    keep: bool = False
) -> DataFrame:
    if isinstance(by, dict):
        right_on=list(by.values())
        ret = pandas.merge(
            x, y,
            left_on=list(by.keys()),
            right_on=right_on,
            how='left',
            copy=copy,
            suffixes=suffix
        )
        if not keep:
            return ret.drop(columns=right_on)
        return ret
    return pandas.merge(x, y, on=by, how='left', copy=copy, suffixes=suffix)

@register_verb(DataFrame)
def right_join(
    x: DataFrame,
    y: DataFrame,
    by: Optional[Union[Iterable[str], Mapping[str, str]]] = None,
    copy: bool = False,
    suffix: Iterable[str] = ("_x", "_y"),
    keep: bool = False
) -> DataFrame:
    if isinstance(by, dict):
        right_on=list(by.values())
        ret = pandas.merge(
            x, y,
            left_on=list(by.keys()),
            right_on=right_on,
            how='right',
            copy=copy,
            suffixes=suffix
        )
        if not keep:
            return ret.drop(columns=right_on)
        return ret
    return pandas.merge(x, y, on=by, how='right', copy=copy, suffixes=suffix)

@register_verb(DataFrame)
def full_join(
    x: DataFrame,
    y: DataFrame,
    by: Optional[Union[Iterable[str], Mapping[str, str]]] = None,
    copy: bool = False,
    suffix: Iterable[str] = ("_x", "_y"),
    keep: bool = False
) -> DataFrame:
    if isinstance(by, dict):
        right_on=list(by.values())
        ret = pandas.merge(
            x, y,
            left_on=list(by.keys()),
            right_on=right_on,
            how='outer',
            copy=copy,
            suffixes=suffix
        )
        if not keep:
            return ret.drop(columns=right_on)
        return ret
    return pandas.merge(x, y, on=by, how='outer', copy=copy, suffixes=suffix)

@register_verb(DataFrame)
def nest_join(
    x: DataFrame,
    y: DataFrame,
    by: Optional[Union[Iterable[str], Mapping[str, str]]] = None,
    copy: bool = False,
    suffix: Iterable[str] = ("_x", "_y"),
    keep: bool = False
) -> DataFrame:
    on = by
    if isinstance(by, (list, tuple, set)):
        on = dict(zip(by, by))
    elif by is None:
        common_cols = list_intersect(x.columns.tolist(), y.columns)
        on = dict(zip(common_cols, common_cols))
    elif not isinstance(by, dict):
        on = {by: by}

    if copy:
        x = x.copy()

    def get_nested_df(row: Series) -> DataFrame:
        condition = None
        for key in on:
            if condition is None:
                condition = y[on[key]] == row[key]
            else:
                condition = condition and (y[on[key]] == row[key])
        df = filter(y, condition)
        if not keep:
            df = df[list_diff(df.columns.tolist(), on.values())]
        if suffix:
            for col in df.columns:
                if col in x:
                    x.rename(columns={col: f'{col}{suffix[0]}'}, inplace=True)
                    df.rename(columns={col: f'{col}{suffix[1]}'}, inplace=True)
        return df

    y_matched = x.apply(lambda row: get_nested_df(row), axis=1)
    y_name = getattr(y, '__dfname__', None)
    if y_name:
        y_matched = y_matched.to_frame(name=y_name)
    return pandas.concat([x, y_matched], axis=1)

@register_verb(DataFrame)
def semi_join(
    x: DataFrame,
    y: DataFrame,
    by: Optional[Union[Iterable[str], Mapping[str, str]]] = None,
    copy: bool = False
) -> DataFrame:
    ret = pandas.merge(x, y, on=by, how='left', copy=copy, indicator=True)
    return ret[ret._merge == 'both'].loc[:, x.columns.tolist()]

@register_verb(DataFrame)
def anti_join(
    x: DataFrame,
    y: DataFrame,
    by: Optional[Union[Iterable[str], Mapping[str, str]]] = None,
    copy: bool = False
) -> DataFrame:
    ret = pandas.merge(x, y, on=by, how='left', copy=copy, indicator=True)
    return ret[ret._merge != 'both'].loc[:, x.columns.tolist()]

@register_verb(DataFrame)
def transpose(_data: DataFrame, copy: bool = False) -> DataFrame:
    return _data.transpose(copy=copy)

t = transpose

@register_verb((DataFrame, DataFrameGroupBy), context=Context.SELECT)
def get(
        _data: Union[DataFrame, DataFrameGroupBy],
        rows: Any = None,
        cols: Any = None
) -> Any:
    _data = objectize(_data)
    # getting single element
    if (
            rows is not None and
            cols is not None and (
                isinstance(rows, str) or
                not isinstance(rows, tuple([*IterableLiterals, builtins.slice]))
            ) and (
                isinstance(cols, str) or
                not isinstance(cols, tuple([*IterableLiterals, builtins.slice]))
            )
    ):
        return _data.loc[rows, cols]

    if rows is not None:
        _data = slice(_data, rows)
    if cols is not None:
        _data = select(_data, cols)
    return _data

@register_verb((DataFrame, DataFrameGroupBy))
def group_map(
        _data: Union[DataFrame, DataFrameGroupBy],
        func: Callable[[DataFrame], Any]
) -> List[Any]:
    if isinstance(_data, DataFrame):
        return func(_data)
    return [
        func(_data.obj.loc[index]) for index in _data.grouper.groups.values()
    ]

@register_verb((DataFrame, DataFrameGroupBy))
def group_modify(
        _data: Union[DataFrame, DataFrameGroupBy],
        func: Callable[[DataFrame], DataFrame]
) -> List[Any]:
    if isinstance(_data, DataFrame):
        return func(_data)
    return _data.apply(func).reset_index(drop=True, level=0)

@register_verb((DataFrame, DataFrameGroupBy))
def group_walk(
        _data: Union[DataFrame, DataFrameGroupBy],
        func: Callable[[DataFrame], None]
) -> List[Any]:
    if isinstance(_data, DataFrame):
        return func(_data)
    return _data.apply(func)

@register_verb(DataFrameGroupBy)
def group_trim(
        _data: DataFrameGroupBy
) -> DataFrameGroupBy:
    return _data.obj.groupby(_data.grouper.names)

@register_verb((DataFrame, DataFrameGroupBy))
def group_split(
        _data: Union[DataFrame, DataFrameGroupBy],
        *cols: str,
        _keep: bool = False,
        **kwargs: Any
) -> DataFrameGroupBy:
    if isinstance(_data, RowwiseDataFrame):
        _data = objectize(_data)
        return [_data.iloc[[i], :] for i in range(_data.shape[0])]

    if isinstance(_data, DataFrameGroupBy):
        return [
            _data.obj.loc[index] for index in _data.grouper.groups.values()
        ]

    _data = group_by(_data, *cols, **kwargs)
    return group_split(_data)

@register_verb((DataFrame, DataFrameGroupBy), context=Context.UNSET)
def with_groups(
        _data: Union[DataFrame, DataFrameGroupBy],
        _groups: Optional[Union[str, Iterable[str]]],
        _func: Callable,
        *args: Any,
        **kwargs: Any
) -> DataFrameGroupBy:
    _groups = evaluate_expr(_groups, _data, Context.SELECT)
    if _groups is not None:
        _data = group_by(_data, _groups)
    else:
        _data = objectize(_data)

    if getattr(_func, '__pipda__', None):
        return _data >> _func(*args, **kwargs)

    return _func(_data, *args, **kwargs)