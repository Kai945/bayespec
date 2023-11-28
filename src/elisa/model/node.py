"""Module containing some helper classes to store model information."""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import reduce, update_wrapper
from typing import Any, Callable, Union
from types import FunctionType
from uuid import uuid4

from numpyro.distributions import Distribution

ModelNodeType = Union['ModelNode', 'ModelOperationNode']
ParameterNodeType = Union['ParameterNode', 'ParameterOperationNode']

_UUID: list[str] = []  # stores uuid that has been used

# __all__ = []


class Node(ABC):
    """Abstract class to store model information.

    Stores information including how model is constructed and the corresponding
    parameters.

    Parameters
    ----------
    name : str
        Name of the node.
    fmt : str
        Tex format of the node.
    is_operation : bool
        Whether the node is generated by operation.
    predecessor : list of Node
        Predecessors of the node.
    attrs : dict
        Attributes of the node.

    """

    def __init__(
        self,
        name: str,
        fmt: str,
        is_operation: bool = False,
        predecessor: list[Node] | None = None,
        attrs: dict[str, Any] | None = None
    ):
        if attrs is None:
            attrs = dict()

        if 'id' in attrs:
            raise TypeError('got multiple values for attribute "id"')

        if 'type' in attrs:
            raise TypeError('got multiple values for attribute "type"')

        if predecessor is None:
            self._predecessor = []
        else:
            self._predecessor = predecessor

        node_id = str(uuid4().hex)

        # check if uuid4 collides, which could result from problems with code
        if node_id in _UUID:
            raise RuntimeError('UUID4 collision found!')

        self._attrs = dict(
            name=name,
            fmt=fmt,
            type=self.type,
            is_operation=is_operation,
            id=node_id
        )
        self._attrs.update(attrs)

    def __repr__(self) -> str:
        return self.name

    @abstractmethod
    def __add__(self, other: Node):
        pass

    @abstractmethod
    def __mul__(self, other: Node):
        pass

    @property
    def name(self) -> str:
        """Node name with id suffix."""
        return self._label_with_id('name')

    @property
    def fmt(self) -> str:
        """Node Tex with id suffix."""
        return self._label_with_id('fmt')

    @property
    @abstractmethod
    def type(self) -> str:
        """Node type."""
        pass

    @property
    def predecessor(self) -> list[Node]:
        """Node predecessors."""
        return self._predecessor

    @property
    def attrs(self) -> dict:
        """Node attributes."""
        return self._attrs

    def _label_with_id(self, label) -> str:
        """Add node id suffix to name or fmt.

        The node id is mainly used in :class:`LabelSpace`, to avoid label
        collision, and the id suffix may be replaced later.

        Parameters
        ----------
        label : {'name', 'fmt'}
            Which label to add suffix.

        Returns
        -------
        str
            Label with suffix added.

        """
        if label != 'name' and label != 'fmt':
            raise ValueError('`label` should be "name" or "fmt"')

        return f'{self.attrs[label]}_{self.attrs["id"]}'


class OperationNode(Node, ABC):
    """Abstract class to handle operation on instance of :class:`Node`.

    Parameters
    ----------
    lh: Node
        Left-hand node operand.
    rh: Node
        Right-hand node operand.
    op : {'+', '*'}
        Operation to perform.

    """

    def __init__(self, lh: Node, rh: Node, op: str):
        self._check_type(lh, rh, op)

        fmt = r'\times' if op == '*' else op

        super().__init__(
            name=op,
            fmt=fmt,
            is_operation=True,
            predecessor=[lh, rh]
        )

    def _label_with_id(self, label: str) -> str:
        """Pretty format `name` or `fmt` by composing operands.

        Parameters
        ----------
        label : {'name', 'fmt'}
            Which label to produce.

        Returns
        -------
        str
            Label in pretty format.

        """
        lh, rh = self.predecessor
        op_name = self.attrs['name']
        op = self.attrs[label]
        lh_label = getattr(lh, label)
        rh_label = getattr(rh, label)

        if op_name == '*':
            if lh.attrs['name'] == '+':
                lh_label = f'({lh_label})'

            if rh.attrs['name'] == '+':
                rh_label = f'({rh_label})'

        return f'{lh_label} {op} {rh_label}'

    @staticmethod
    def _check_type(lh: Node, rh: Node, op: str) -> str:
        """Check if lh and rh are correct.

        Parameters
        ----------
        lh: Node
            Left-hand node operand.
        rh: Node
            Right-hand node operand.
        op : {'+', '*'}
            Operation to perform.

        Raises
        ------
        TypeError
            Raised when
                - `op` is not + or *
                - `lh` or `rh` is not Node type
                - type of `lh` and `rh` not matched

        """
        if op not in {'+', '*'}:
            raise TypeError(f'operator "{op}" is not supported')

        if not isinstance(lh, Node):
            raise TypeError(f'got wrong input {lh}')

        if not isinstance(rh, Node):
            raise TypeError(f'got wrong input {rh}')

        type1 = lh.type
        type2 = rh.type
        if type1 != type2:
            raise TypeError(
                f'unsupported types for {op}: "{type1}" and "{type2}"'
            )

        return type1


class ParameterNode(Node):
    """Class to handle parameter definition and construction.

    Parameters
    ----------
    name : str
        Name of the parameter.
    fmt : str
        Tex format of the parameter.
    default : float
        Default value of the parameter.
    distribution : Distribution
        Instance of :class:`numpyro.distributions.Distribution`.
    deterministic : tuple, optional
        Information required to call :meth:`numpyro.deterministic`. It is a
        tuple with two elements, the first is a tuple of str and the second is
        a function, whose arguments is the same length of the tuple.

    """

    def __init__(
        self,
        name: str,
        fmt: str,
        default: float | int,
        distribution: Distribution | float | int,
        deterministic: tuple | None = None
    ):
        self._validate_input(distribution, deterministic)

        self._validate_default(distribution, default)

        attrs = dict(
            default=default,
            distribution=distribution,
            deterministic=deterministic
        )

        super().__init__(name=name, fmt=fmt, attrs=attrs)

    def __add__(self, other: ParameterNodeType) -> ParameterOperationNode:
        return ParameterOperationNode(self, other, '+')

    def __mul__(self, other: ParameterNodeType) -> ParameterOperationNode:
        return ParameterOperationNode(self, other, '*')

    @property
    def type(self) -> str:
        """Node type is parameter."""
        return 'parameter'

    @property
    def default(self) -> float:
        """Default value of the parameter."""
        return self.attrs['default']

    @default.setter
    def default(self, value: float):
        """Default value of the parameter."""
        value = float(value)
        self._validate_default(self.attrs['distribution'], value)
        self.attrs['default'] = value

    @property
    def site(self) -> dict:
        """Sample and deterministic site information of :mod:`numpyro`."""
        name = self.name

        info = {
            'sample': {name: self.attrs['distribution']},
            'deterministic': {}
        }

        if self.attrs['deterministic'] is not None:
            (deterministic_fmt,), func = self.attrs['deterministic']
            deterministic_fmt = deterministic_fmt.format(name=name)
            info['deterministic'][deterministic_fmt] = ((name,), func)

        return info

    @staticmethod
    def _validate_input(
        dist: Distribution | float | int,
        determ: tuple | None
    ) -> None:
        """Validate if input is correct."""
        if not isinstance(dist, (Distribution, float, int)):
            raise ValueError(
                'dist must be a numpyro Distribution instance, or a float'
            )

        if determ is not None:
            if not isinstance(determ, (list, tuple)):
                raise ValueError('deterministic must be list or tuple')

            if len(determ) != 2 \
                    or not isinstance(determ[0], (list, tuple))\
                    or not callable(determ[1]):
                raise ValueError(
                    'deterministic should contain a tuple and a function'
                )

            if not all(isinstance(i, str) for i in determ[0]):
                raise ValueError(
                    'elements of deterministic[0] should be str'
                )

    @staticmethod
    def _validate_default(
        dist: Distribution | float | int,
        default: float | int,
    ) -> None:
        """Validate if default is in distribution domain."""
        if isinstance(dist, Distribution):
            if not dist._validate_sample(default):
                raise ValueError('default value outside the dist domain')

        else:  # isinstance(dist, (float, int))
            if dist != default:
                raise ValueError('default value and fixed dist are different')


class ParameterOperationNode(OperationNode):
    """Class to handle parameter operation.

    Parameters
    ----------
    lh: Node
        Left-hand parameter node.
    rh: Node
        Right-hand parameter node.
    op : {'+', '*'}
        Operation to perform.

    """

    predecessor: list[ParameterNodeType]

    def __init__(self, lh: ParameterNodeType, rh: ParameterNodeType, op: str):
        super().__init__(lh, rh, op)

    def __add__(self, other: ParameterNodeType) -> ParameterOperationNode:
        return ParameterOperationNode(self, other, '+')

    def __mul__(self, other: ParameterNodeType) -> ParameterOperationNode:
        return ParameterOperationNode(self, other, '*')

    @property
    def type(self) -> str:
        """Node type is parameter."""
        return 'parameter'

    @property
    def default(self) -> float:
        """Default value of the parameter operation."""
        lh = self.predecessor[0].default
        rh = self.predecessor[1].default

        if self.attrs['name'] == '+':
            return lh + rh
        else:
            return lh * rh

    @property
    def site(self) -> dict:
        """Sample and deterministic site information of :mod:`numpyro`."""
        name = self.name

        lh_name = self.predecessor[0].name
        rh_name = self.predecessor[1].name

        lh = self.predecessor[0].site
        rh = self.predecessor[1].site

        info = {
            'sample': {**lh['sample'], **rh['sample']},
            'deterministic': {**lh['deterministic'], **rh['deterministic']},
        }
        deterministic = info['deterministic']

        operand_name = (lh_name, rh_name)
        if self.attrs['name'] == '+':
            deterministic[name] = (operand_name, lambda x, y: x + y)
        else:
            deterministic[name] = (operand_name, lambda x, y: x * y)

        return info


class ModelNode(Node):
    """Class to handle model definition and construction.

    Parameters
    ----------
    name : str
        Name of the model.
    fmt : str
        Tex format of the model.
    mtype : {'add', 'mul', 'con'}
        Model type.
    params : dict
        A str-parameter mapping that defines the parameters of the model.
    func_generator : callable
        Generator of model function.
    is_ncon : bool
        Whether model is normalization convolution type.

    Notes
    -----
    The signature of `func` should be ``func(egrid, par1, ...)``, where
    `func` is expected to return ndarray of length ``len(egrid) - 1`` (i.e.,
    integrating over `egrid`), and ``par1, ...`` matches `params`.

    If the function is convolution type, operating on flux (con) or norm
    (ncon), then corresponding signature of `func` should be
    ``func(egrid, flux, par1, ...)`` or ``func(flux_func, flux, par1, ...)``,
    where `flux` is ndarray of length ``len(egrid) - 1``, and `flux_func` has
    the same signature and returns as aforementioned.

    """

    predecessor: list[ParameterNodeType]

    def __init__(
        self,
        name: str,
        fmt: str,
        mtype: str,
        params: dict[str, ParameterNodeType],
        func_generator: Callable,
        is_ncon: bool
    ):
        if mtype not in {'add', 'mul', 'con'}:
            raise TypeError(f'unrecognized model type "{mtype}"')

        if params is None:
            predecessor = None
            self._params_name = tuple()
        else:
            for v in params.values():
                if not isinstance(v, (ParameterNode, ParameterOperationNode)):
                    raise ValueError(f'{v} is not Parameter type')

            self._params_name = tuple(params.keys())
            predecessor = list(params.values())

        attrs = dict(
            mtype=mtype,
            func_generator=func_generator,
            is_ncon=is_ncon
        )

        super().__init__(
            name=name,
            fmt=fmt,
            predecessor=predecessor,
            attrs=attrs
        )

    def __add__(self, other: ModelNodeType) -> ModelOperationNode:
        return ModelOperationNode(self, other, '+')

    def __mul__(self, other: ModelNodeType) -> ModelOperationNode:
        return ModelOperationNode(self, other, '*')

    @property
    def type(self) -> str:
        """Node type is model."""
        return 'model'

    @property
    def params(self) -> dict[str, str]:
        """Parameter dict."""
        return {
            self.name: {
                pname: node.name
                for pname, node in zip(self._params_name, self.predecessor)
            }
        }

    @property
    def comps(self) -> tuple:
        """Model components name."""
        return (self.name,)

    @property
    def site(self) -> dict:
        """Sample and deterministic site information of :mod:`numpyro`."""
        sites = [p.site for p in self.predecessor]

        sample = [s['sample'] for s in sites]
        sample = reduce(lambda i, j: {**i, **j}, sample)

        deterministic = [s['deterministic'] for s in sites]
        deterministic = reduce(lambda i, j: {**i, **j}, deterministic)

        return {'sample': sample, 'deterministic': deterministic}

    def generate_func(self, mapping: dict[str, str]) -> Callable:
        """Wrap model evaluation function."""
        model_name = str(mapping[self.name])
        func = self.attrs['func_generator'](model_name)

        # from https://stackoverflow.com/a/13503277
        copy = FunctionType(
            code=func.__code__,
            globals=func.__globals__,
            name=model_name,
            argdefs=func.__defaults__,
            closure=func.__closure__
        )
        copy = update_wrapper(copy, func)
        copy.__kwdefaults__ = func.__kwdefaults__
        func = copy

        mtype = self.attrs['mtype']

        # notation: p=params, e=egrid, f=flux, ff=flux_func
        # params structure should be {model_id: {param1: ..., param2: ...}}
        if mtype == 'add':
            def wrapper_add(p, e, *_):
                """Evaluate add model."""
                return func(e, **p[model_name])

            return wrapper_add

        elif mtype == 'mul':
            def wrapper_mul(p, e, *_):
                """Evaluate mul model."""
                return func(e, **p[model_name])

            return wrapper_mul

        else:  # mtype == 'con'
            if self.attrs['is_ncon']:
                def wrapper_ncon(p, _=None, f=None, ff=None):
                    """Evaluate ncon model, f and ff must be provided."""
                    return func(ff, f, **p[model_name])

                return wrapper_ncon

            else:
                def wrapper_con(p, e, f, *_):
                    """Evaluate con model."""
                    return func(e, f, **p[model_name])

                return wrapper_con


class ModelOperationNode(OperationNode):
    """Class to handle model operation.

    Parameters
    ----------
    lh: Node
        Left-hand model node.
    rh: Node
        Right-hand model node.
    op : {'+', '*'}
        Operation to perform.

    """

    predecessor: list[ModelNodeType]

    def __init__(self, lh: ModelNodeType, rh: ModelNodeType, op: str):
        self._check_type(lh, rh, op)

        mtype1 = lh.attrs['mtype']
        mtype2 = rh.attrs['mtype']

        # check if operand is legal for the op
        if op == '+':
            if mtype1 != 'add':
                raise TypeError(f'{lh} is not additive')

            if mtype2 != 'add':
                raise TypeError(f'{rh} is not additive')

        else:  # op == '*'
            if mtype1 == 'add':
                if mtype2 == 'add':
                    raise TypeError(
                        f'unsupported types for *: {lh} (add) and {rh} (add)'
                    )
                elif mtype2 == 'con':
                    raise TypeError(
                        f'unsupported order for *: {lh} (add) and {rh} (con)'
                    )

            if lh.attrs['is_ncon'] and rh.attrs['is_ncon']:
                raise TypeError(
                    f'unsupported types for *: {lh} (ncon) and {rh} (ncon), '
                    f'norm convolution can only be used once for one component'
                )

        is_ncon = False

        # determine the mtype
        if mtype1 == 'add' or mtype2 == 'add':
            mtype = 'add'
        else:
            if mtype1 == 'con' or mtype2 == 'con':
                mtype = 'con'
                if lh.attrs['is_ncon'] or rh.attrs['is_ncon']:
                    is_ncon = True
            else:
                mtype = 'mul'

        super().__init__(lh, rh, op)
        self.attrs['mtype'] = mtype
        self.attrs['is_ncon'] = is_ncon

        # for a convolution model, fmt is *
        if not isinstance(lh, ModelOperationNode) and \
                lh.attrs.get('mtype', '') == 'con':
            self.attrs['fmt'] = '*'

    def __add__(self, other: ModelNodeType) -> ModelOperationNode:
        return ModelOperationNode(self, other, '+')

    def __mul__(self, other: ModelNodeType) -> ModelOperationNode:
        return ModelOperationNode(self, other, '*')

    @property
    def type(self) -> str:
        """Node type is model."""
        return 'model'

    @property
    def params(self) -> dict[str, ParameterNodeType]:
        """Parameter dict."""
        lh, rh = self.predecessor
        return {**lh.params, **rh.params}

    @property
    def comps(self) -> dict[str, ModelNode]:
        """Model component dict."""
        lh, rh = self.predecessor
        return lh.comps + rh.comps

    @property
    def site(self) -> dict:
        """Sample and deterministic site information of :mod:`numpyro`."""
        lh, rh = self.predecessor
        lh = lh.site
        rh = rh.site

        sample = {**lh['sample'], **rh['sample']}
        deterministic = {**lh['deterministic'], **rh['deterministic']}

        return {'sample': sample, 'deterministic': deterministic}

    def generate_func(self, mapping: dict[str, str]) -> Callable:
        """Wrap model evaluation function."""
        op = self.attrs['name']
        lh, rh = self.predecessor
        m1 = lh.generate_func(mapping)
        m2 = rh.generate_func(mapping)
        type1 = lh.attrs['mtype']
        type2 = rh.attrs['mtype']

        # notation: p=params, e=egrid, f=flux, ff=flux_func
        if op == '+':
            def wrapper_add_add(p, e, *_):
                """add + add"""
                return m1(p, e) + m2(p, e)

            return wrapper_add_add

        if type1 != 'con':  # type1 is add or mul
            if type2 != 'con':  # type2 is add or mul
                def wrapper_op(p, e, *_):  # add * add not allowed
                    """add * mul, mul * add, mul * mul"""
                    return m1(p, e) * m2(p, e)

                return wrapper_op

            else:  # type2 is con
                if rh.attrs['is_ncon']:  # type2 is ncon
                    def wrapper_mul_ncon(p, e, f, ff):
                        """mul * ncon"""
                        return m1(p, e) * m2(p, e, f, ff)

                    return wrapper_mul_ncon

                else:  # type2 is con
                    def wrapper_mul_con(p, e, f, *_):
                        """mul * con"""
                        return m1(p, e) * m2(p, e, f)

                    return wrapper_mul_con

        else:  # type1 is con
            if lh.attrs['is_ncon']:  # type1 is ncon
                if type2 == 'add':
                    def wrapper_ncon_add(p, e, *_):
                        """ncon * add"""
                        return m1(p, e, m2(p, e), m2)

                    return wrapper_ncon_add

                elif type2 == 'mul':
                    def wrapper_ncon_mul(e, p, f, ff):
                        """ncon * mul"""
                        def m2_ff(e_, p_, *_):
                            """mul * add, this will be * by ncon"""
                            return m2(e_, p_) * ff(e_, p_)

                        return m1(p, e, m2(e, p) * f, m2_ff)

                    return wrapper_ncon_mul

                else:  # type2 == 'con'
                    def wrapper_ncon_con(p, e, f, ff):
                        """ncon * con"""
                        def m2_ff(p_, e_, *_):
                            """con * add, this will be * by ncon"""
                            return m2(p_, e_, ff(p_, e_))

                        return m1(p, e, m2(p, e, f), m2_ff)

                    return wrapper_ncon_con

            else:  # type1 is con
                if type2 == 'add':
                    def wrapper_con_add(p, e, *_):
                        """con * add"""
                        return m1(p, e, m2(p, e))

                    return wrapper_con_add

                elif type2 == 'mul':
                    def wrapper_con_mul(p, e, f, *_):
                        """con * mul"""
                        return m1(p, e, m2(p, e) * f)

                    return wrapper_con_mul

                else:
                    if rh.attrs['is_ncon']:
                        def wrapper_con_ncon(p, e, f, ff):
                            """con * ncon"""
                            return m1(p, e, m2(p, e, f, ff))

                        return wrapper_con_ncon

                    else:
                        def wrapper_con_con(p, e, f, *_):
                            """con * con"""
                            return m1(p, e, m2(p, e, f))

                        return wrapper_con_con


class LabelSpace:
    """Class to handle label space of model or parameter composition.

    Parameters
    ----------
    node : Node
        The node to be handled.

    """

    def __init__(self, node: Node):

        self.node = node

        self._label_space = {
            'name': self._get_sub_nodes_label('name'),
            'fmt': self._get_sub_nodes_label('fmt')
        }

        self._label_map = {
            'name': self._get_suffix_mapping('name'),
            'fmt': self._get_suffix_mapping('fmt')
        }

    @property
    def name(self) -> str:
        """Node name with node id replaced by number."""
        return self._label('name')

    @property
    def fmt(self) -> str:
        """Node fmt with node id replaced by number."""
        return self._label('fmt')

    @staticmethod
    def _check_label_type(label_type) -> None:
        """Check if label_type is name or fmt."""
        if label_type != 'name' and label_type != 'fmt':
            raise ValueError('`label_type` should be "name" or "fmt"')

    def _get_sub_nodes_label(self, label_type) -> list[tuple]:
        """Get the address and the name/fmt of sub-nodes.

        Parameters
        ----------
        label_type : {'name', 'fmt'}
            Label type.

        Returns
        -------
        list of tuple
            Returns list[tuple[ModelNodeType, str]].

        """
        self._check_label_type(label_type)

        labels = []
        node_stack = [self.node]

        while node_stack:
            i = node_stack.pop(0)

            if not i.attrs['is_operation']:
                # record address, name and fmt of the sub-node
                labels.append((i, i.attrs[label_type]))

            else:  # add predecessors of operation node to the node stack
                node_stack = i.predecessor + node_stack

        return labels

    def _get_suffix_mapping(self, label_type: str) -> dict[str, str]:
        """Solve label collision of sub-nodes and return suffix mapping.

        Parameters
        ----------
        label_type : {'name', 'fmt'}
            Label to be handled.

        Returns
        -------
        dict
            Node id to number mapping.

        """
        self._check_label_type(label_type)

        label_space = {}
        id_to_str = {}
        node_stack = [self.node]

        while node_stack:
            i = node_stack.pop(0)

            if not i.attrs['is_operation']:
                label = i.attrs[label_type]
                id_ = i.attrs['id']

                # check label collision
                if label not in label_space:  # no label collision found
                    label_space[label] = [id_]  # record label and node id
                    id_to_str[f'{label}_{id_}'] = label

                else:  # there is a label collision
                    same_label_nodes = label_space[label]

                    if id_ not in same_label_nodes:  # not cause by node itself
                        same_label_nodes.append(id_)  # record node id
                        num = len(same_label_nodes)

                        if label_type == 'name':
                            str_ = f'{num}'
                        else:
                            str_ = f'_{num}'
                        id_to_str[f'{label}_{id_}'] = f'{label}{str_}'

            else:  # push predecessors to the node stack
                node_stack = i.predecessor + node_stack

        return id_to_str

    @property
    def mapping(self) -> dict:
        """Label space of name and fmt."""
        # name is not allowed to be changed in our case, ok to check fmt only
        self._check_if_label_changed('fmt')

        return self._label_map

    def _label(self, label_type: str) -> str:
        """Return name/fmt with node id replaced by number"""
        self._check_if_label_changed(label_type)

        label = getattr(self.node, label_type)

        for k, v in self._label_map[label_type].items():
            label = label.replace(k, v)

        return label

    def _check_if_label_changed(self, label: str):
        """Check if the name/fmt of sub-nodes changed."""
        flag = False
        for node, l in self._label_space[label]:
            if node.attrs[label] != l:
                flag = True
                break

        # if changed, reset label space and id to suffix mapping
        if flag:
            self._label_space[label] = self._get_sub_nodes_label(label)
            self._label_map[label] = self._get_suffix_mapping(label)
