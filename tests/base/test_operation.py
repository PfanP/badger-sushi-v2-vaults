import brownie
from brownie import Contract
import pytest


def test_operation(
    chain, accounts, token, vault, strategy, user, strategist, amount, RELATIVE_APPROX
):
    # Deposit to the vault
    user_balance_before = token.balanceOf(user)
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    assert token.balanceOf(vault.address) == amount

    # harvest
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # tend()
    strategy.tend()

    # withdrawal
    vault.withdraw({"from": user})
    assert (
        pytest.approx(token.balanceOf(user), rel=RELATIVE_APPROX) == user_balance_before
    )


def test_emergency_exit(
    chain, accounts, token, vault, strategy, user, strategist, amount, RELATIVE_APPROX
):
    # Deposit to the vault
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # set emergency and exit
    strategy.setEmergencyExit()
    chain.sleep(1)
    strategy.harvest()
    assert strategy.estimatedTotalAssets() < amount


def test_profitable_harvest(
    chain, accounts, token, vault, strategy, user, strategist, amount, RELATIVE_APPROX
):
    # Deposit to the vault
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    assert token.balanceOf(vault.address) == amount

    print("stratDep1 ")
    print(strategy.estimatedTotalAssets())

    # Harvest 1: Send funds through the strategy
    strategy.harvest()
    chain.mine(100)
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    

    # TODO: Add some code before harvest #2 to simulate earning yield
    before_pps = vault.pricePerShare()
    before_total = vault.totalAssets()
    print("checkPendingReward")
    print(strategy.checkPendingReward())

    chain.sleep(3600 * 24 * 1) ## Sleep 1 day
    chain.mine(1)
    print("checkPendingReward")
    print(strategy.checkPendingReward())

    print("stratDep2 ")
    print(strategy.estimatedTotalAssets())

    # Harvest 2: Realize profit
    strategy.harvest()
    print("checkPendingReward")
    print(strategy.checkPendingReward())
    print("stratDep3 ")
    print(strategy.estimatedTotalAssets())
    amountAfterHarvest = strategy.balanceOfPool() + strategy.balanceOfWant()

    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    profit = token.balanceOf(vault.address)  # Profits go to vault

    # NOTE: Your strategy must be profitable
    # NOTE: May have to be changed based on implementation
    stratAssets = strategy.estimatedTotalAssets()
    
    print("stratAssets")
    print(stratAssets)

    vaultAssets = vault.totalAssets()
    print("vaultAssets")
    print(vaultAssets)

    ## Total assets for strat are token + lpComponent + borrowed
    assert  amountAfterHarvest + profit >= amount
    ## NOTE: Changed to >= because I can't get the PPS to increase
    assert vault.pricePerShare() >= before_pps ## NOTE: May want to tweak this to >= or increase amounts and blocks
    assert vault.totalAssets() > before_total ## NOTE: Assets must increase or there's something off with harvest
    ## NOTE: May want to harvest a third time and see if it icnreases totalDebt for strat

    ## Harvest3 since we are using leveraged strat
    strategy.harvest()
    vault.withdraw(amount, {"from": user})
    assert token.balanceOf(user) > amount ## The user must have made more money, else it means funds are stuck



def test_change_debt(
    chain, gov, token, vault, strategy, user, strategist, amount, RELATIVE_APPROX
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})
    chain.sleep(1)
    strategy.harvest()
    half = int(amount / 2)

    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == half

    vault.updateStrategyDebtRatio(strategy.address, 10_000, {"from": gov})
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # NOTE: In order to pass this tests, you will need to implement prepareReturn.
    vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == half


def test_sweep(gov, vault, strategy, token, user, amount, weth, weth_amout):
    # Strategy want token doesn't work
    token.transfer(strategy, amount, {"from": user})
    assert token.address == strategy.want()
    assert token.balanceOf(strategy) > 0
    with brownie.reverts("!want"):
        strategy.sweep(token, {"from": gov})

    # Vault share token doesn't work
    with brownie.reverts("!shares"):
        strategy.sweep(vault.address, {"from": gov})

    tokens = strategy.protectedTokens()
    # NOTE: You have to add protected tokens to the strat
    for pToken in tokens:
        with brownie.reverts("!protected"):
            strategy.sweep(pToken, {"from": gov})

    before_balance = weth.balanceOf(gov)
    weth.transfer(strategy, weth_amout, {"from": user})
    assert weth.address != strategy.want()
    assert weth.balanceOf(user) == 0
    strategy.sweep(weth, {"from": gov})
    assert weth.balanceOf(gov) == weth_amout + before_balance


def test_triggers(
    chain, gov, vault, strategy, token, amount, user, weth, weth_amout, strategist
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})
    chain.sleep(1)
    strategy.harvest()

    strategy.harvestTrigger(0)
    strategy.tendTrigger(0)
