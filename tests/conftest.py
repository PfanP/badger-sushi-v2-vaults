import pytest
from brownie import config
from brownie import Contract

## SET These Variables up for the testing suite
WANT = "0xE62Ec2e799305E0D367b0Cc3ee2CdA135bF89816" ## WBTC<-> WETH
LP_COMPONENT = "0x0769fd68dFb93167989C6f7254cd0D766Fb2841F" ## aDAI
REWARD_TOKEN = "0x0b3F868E0BE5597D5DB7fEB59E1CADBb0fdDa50a" ## Sushi Token

PROTECTED_TOKENS = [WANT, LP_COMPONENT, REWARD_TOKEN]
## Fees in Basis Points
DEFAULT_GOV_PERFORMANCE_FEE = 1000 ## TODO: Add to Vault.initialize
DEFAULT_PERFORMANCE_FEE = 1000
DEFAULT_WITHDRAWAL_FEE = 75 ## TODO: Add to Vault setWithdrawalFee

## NOTE: There's a few more things you may need to change below, try running tests and adapt


@pytest.fixture
def gov(accounts):
    yield accounts.at("0xb65cef03b9b89f99517643226d76e286ee999e77", force=True)


@pytest.fixture
def user(accounts):
    yield accounts[0]


@pytest.fixture
def rewards(accounts):
    yield accounts[1]


@pytest.fixture
def guardian(accounts):
    yield accounts[2]


@pytest.fixture
def management(accounts):
    yield accounts[3]


@pytest.fixture
def strategist(accounts):
    yield accounts[4]


@pytest.fixture
def keeper(accounts):
    yield accounts[5]


## Base tests call it token, badger tests call it want
@pytest.fixture
def token():
    token_address = WANT  # this should be the address of the ERC-20 used by the strategy/vault (DAI)
    yield Contract(token_address)


@pytest.fixture
def want(token):
    yield token

@pytest.fixture
def lpComponent():
    lp_address = LP_COMPONENT
    yield Contract(lp_address)


@pytest.fixture
def reward():
    reward_address = REWARD_TOKEN
    yield Contract(reward_address)

@pytest.fixture
def amount(accounts, token, user):
    amount = 0.0005* (10 ** token.decimals())
    
    # In order to get some funds for the token you are about to use,
    # it impersonate an exchange address to use it's funds.
    ## TODO: Change this to an address with at least `amount` of want
    reserve = accounts.at("0x0769fd68dfb93167989c6f7254cd0d766fb2841f", force=True)
    token.transfer(user, amount, {"from": reserve})
    yield amount


@pytest.fixture
def weth():
    token_address = "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270"
    yield Contract(token_address)


@pytest.fixture
def weth_amout(user, weth):
    weth_amout = 10 ** weth.decimals()
    user.transfer(weth, weth_amout)
    yield weth_amout


@pytest.fixture
def vault(pm, gov, rewards, guardian, management, token):
    Vault = pm(config["dependencies"][0]).Vault
    vault = guardian.deploy(Vault)
    vault.initialize(token, gov, rewards, "", "", guardian, management)
    vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
    vault.setManagement(management, {"from": gov})
    yield vault


@pytest.fixture
def strategy(strategist, keeper, vault, Strategy, gov):
    strategy = strategist.deploy(Strategy)
    strategy.initialize(vault, strategist, strategist, strategist)
    strategy.setKeeper(keeper)
    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, DEFAULT_PERFORMANCE_FEE, {"from": gov})
    yield strategy


@pytest.fixture(scope="session")
def RELATIVE_APPROX():
    yield 1e-5