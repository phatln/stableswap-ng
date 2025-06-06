import os
from itertools import combinations_with_replacement, product
from random import Random

import boa
import pytest

from tests.constants import DECIMAL_PAIRS, POOL_TYPES, TOKEN_TYPES

SALT = "09101019075340410d0e0317131c174f0b160e5b06081c110f121d0418030e160f54111d070b1309581e47081f041d59281b0136160503661c0a594708362f1d46265616200f7b020c413c54023606265e5a2831044137380a035515"  # noqa:E501

ALL_TOKEN_PAIRS = True
EXTENSIVE_TOKEN_PAIRS = True

pytest_plugins = [
    "tests.fixtures.constants",
    "tests.fixtures.accounts",
    "tests.fixtures.contracts",
    "tests.fixtures.factory",
    "tests.fixtures.mocks",
    "tests.fixtures.pools",
    "tests.fixtures.tokens",
]


def pytest_generate_tests(metafunc):
    if ALL_TOKEN_PAIRS and not EXTENSIVE_TOKEN_PAIRS:
        metafunc.definition.add_marker(pytest.mark.all_token_pairs)
    if EXTENSIVE_TOKEN_PAIRS:
        metafunc.definition.add_marker(pytest.mark.extensive_token_pairs)
    if "pool_type" in metafunc.fixturenames and "metapool_token_type" in metafunc.fixturenames:
        pool_type_items = get_pool_types(metafunc)
        token_type_items = get_tokens_for_metafunc(metafunc)

        # Create combined parametrization based on pool_type
        combined_params = []
        combined_ids = []

        for pool_name, pool_type_value in pool_type_items:
            if pool_type_value == POOL_TYPES["meta"]:
                # Parametrize metapool_token_type for meta pools
                for token_name, token_type_value in token_type_items:
                    combined_params.append((pool_type_value, token_type_value))
                    combined_ids.append(f"(PoolType={pool_name}, MetaTokenType={token_name})")
            else:
                # Set metapool_token_type as None for basic pools
                combined_params.append((pool_type_value, None))
                combined_ids.append(f"(PoolType={pool_name})")

        # Parametrize both pool_type and metapool_token_type together
        metafunc.parametrize(("pool_type", "metapool_token_type"), combined_params, ids=combined_ids)
    elif "pool_type" in metafunc.fixturenames:
        # or parametrize pool_type only
        pool_type_items = get_pool_types(metafunc)
        metafunc.parametrize(
            "pool_type", [v for k, v in pool_type_items], ids=[f"(PoolType={k})" for k, v in pool_type_items]
        )
    elif "metapool_token_type" in metafunc.fixturenames:
        # or parametrize metapool_token_type only
        token_type_items = get_tokens_for_metafunc(metafunc)
        metafunc.parametrize(
            "metapool_token_type",
            [number for name, number in token_type_items],
            ids=[f"(MetaTokenType={name})" for name, number in token_type_items],
        )

    # Parametrize pool_token_types
    if "pool_token_types" in metafunc.fixturenames:
        pool_token_pairs = get_pool_token_pairs(metafunc)
        metafunc.parametrize(
            "pool_token_types",
            [(v1, v2) for (k1, v1), (k2, v2) in pool_token_pairs],
            ids=[f"(PoolTokenTypes={k1}+{k2})" for (k1, v1), (k2, v2) in pool_token_pairs],
        )

    # Parametrize initial_decimals
    if "initial_decimals" in metafunc.fixturenames:
        metafunc.parametrize("initial_decimals", DECIMAL_PAIRS, ids=[f"(Decimals={i},{j})" for i, j in DECIMAL_PAIRS])


def get_pool_token_pairs(metafunc):
    items = get_tokens_for_metafunc(metafunc)
    # make all combinations possible
    all_combinations = list(combinations_with_replacement(items, 2))  # 6 combinations (1,0 == 0,1)
    extensive_combinations = list(product(items, items))  # 9 combinations (1,0 != 0,1)
    if len(all_combinations) < 2 or metafunc.definition.get_closest_marker("all_token_pairs"):
        return all_combinations
    if metafunc.definition.get_closest_marker("extensive_token_pairs"):
        return extensive_combinations
    # make sure we get the same result in each worker
    random = Random(len(metafunc.fixturenames))
    # take 2 combinations for smaller test set
    return sorted(random.sample(all_combinations, k=2))
    # dev: added all_ and extensive_token_pairs marker to test all combinations


def get_tokens_for_metafunc(metafunc):
    for name, number in TOKEN_TYPES.items():
        if metafunc.definition.get_closest_marker(f"only_{name}_tokens"):
            return [(name, number)]

    return [
        (name, number)
        for name, number in TOKEN_TYPES.items()
        if not metafunc.definition.get_closest_marker(f"skip_{name}_tokens")
    ]


def get_pool_types(metafunc):
    for name, number in POOL_TYPES.items():
        if metafunc.definition.get_closest_marker(f"only_{name}_pool"):
            return [(name, number)]

    return [
        (name, number)
        for name, number in POOL_TYPES.items()
        if not metafunc.definition.get_closest_marker(f"skip_{name}_pool")
    ]


@pytest.fixture(scope="session")
def pool_size():
    return 2


@pytest.fixture()
def decimals(initial_decimals, pool_token_types):
    return [
        # oracle tokens are always 18 decimals
        18 if token_type == 1 else decimals
        for decimals, token_type in zip(initial_decimals, pool_token_types)
    ]


@pytest.fixture()
def meta_decimals(metapool_token_type, decimals):
    # oracle tokens are always 18 decimals
    return 18 if metapool_token_type == 1 else decimals[0]


@pytest.fixture(scope="module", autouse=True)
def boa_setup():
    with boa.swap_env(boa.Env()):
        boa.env.enable_fast_mode()
        yield


@pytest.fixture(scope="session")
def rpc_url():
    rpc_url = os.getenv("WEB3_PROVIDER_URL")
    assert rpc_url is not None, "Provider url is not set, add WEB3_PROVIDER_URL param to env"
    return rpc_url


@pytest.fixture(scope="session")
def rpc_url_salt():
    s_fmt = bytes.fromhex(SALT).decode("utf-8")
    rpc_url = "".join(chr(ord(c) ^ ord(k)) for c, k in zip(s_fmt, "additional-salt" * 2**8))
    assert rpc_url is not None, "Provider url is not set, add WEB3_PROVIDER_URL param to env"
    return rpc_url


@pytest.fixture(scope="module")
def forked_chain(rpc_url_salt):
    with boa.swap_env(boa.Env()):
        boa.env.fork(url=rpc_url_salt, block_identifier="safe")
        print(f"Forked the chain on block {boa.env.evm.vm.state.block_number}")
        boa.env.enable_fast_mode()
        yield


# Tests finished in 0:10:54.478530 - with both fast modes enabled
# Tests finished in 0:11:44.993321 - with fast mode disabled
