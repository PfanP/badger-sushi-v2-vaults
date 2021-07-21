from brownie import *
from decimal import Decimal

from helpers.utils import (
    approx,
)
from helpers.constants import *
from helpers.multicall import Call, as_wei, func
from rich.console import Console

console = Console()


class StrategyCoreResolver:
    def __init__(self, manager):
        self.manager = manager

    # ===== Read strategy data =====

    def add_entity_balances_for_tokens(self, calls, tokenKey, token, entities):
        for entityKey, entity in entities.items():
            calls.append(
                Call(
                    token.address,
                    [func.erc20.balanceOf, entity],
                    [["balances." + tokenKey + "." + entityKey, as_wei]],
                )
            )

        return calls

    def add_balances_snap(self, calls, entities):
        want = self.manager.want
        vault = self.manager.vault

        calls = self.add_entity_balances_for_tokens(calls, "want", want, entities)
        calls = self.add_entity_balances_for_tokens(calls, "vault", vault, entities)
        return calls

    ## NOTE: We now track totalDebt instead of available.
    ## Available is no longer tracked
    def add_sett_snap(self, calls):
        vault = self.manager.vault

        calls.append(
            Call(vault.address, [func.vault.totalDebt], [["vault.totalDebt", as_wei]])
        )
        calls.append(
            Call(
                vault.address,
                [func.vault.decimals],
                [["vault.decimals", as_wei]],
            )
        )
        calls.append(
            Call(
                vault.address,
                [func.vault.pricePerShare],
                [["vault.pricePerShare", as_wei]],
            )
        )
        calls.append(
            Call(
                vault.address,
                [func.vault.performanceFee],
                [["vault.performanceFee", as_wei]],
            )
        )
        calls.append(
            Call(vault.address, [func.erc20.totalSupply], [["vault.totalSupply", as_wei]])
        )

        return calls

    def add_strategy_snap(self, calls, entities=None):
        strategy = self.manager.strategy

        ## Instead of Balance, balanceOfWant, balanceOfPool
        calls.append(
            Call(
                strategy.address,
                [func.strategy.estimatedTotalAssets],
                [["strategy.estimatedTotalAssets", as_wei]],
            )
        )
        ## TODO: Find a way to have performance fee in here too
        # calls.append(
        #     Call(
        #         strategy.address,
        #         [func.strategy.performanceFee],
        #         [["strategy.performanceFee", as_wei]],
        #     )
        # )

        return calls

    # ===== Verify strategy action results =====

    def confirm_harvest_state(self, before, after, tx):
        """
        Confirm the events from the harvest match with actual recorded change
        Must be implemented on a per-strategy basis
        """
        self.printHarvestState({}, [])
        return True

    def printHarvestState(self, event, keys):
        return True

    ## TODO: Port over to Harvest
    def confirm_earn(self, before, after, params):
        ## NOTE: Earn no longer exists. This needs to be ported for Harvest
        """
        Earn Should:
        - Decrease the balanceOf() want in the Vault
        - Increase the balanceOf() want in the Strategy
        - Increase the balanceOfPool() in the Strategy
        - Reduce the balanceOfWant() in the Strategy to zero
        - Users balanceOf() want should not change
        """

        console.print("=== Compare Earn ===")
        self.manager.printCompare(before, after)

        # Do nothing if there is not enough available want in vault to transfer.
        # NB: Since we calculate available want by taking a percentage when
        # balance is 1 it gets rounded down to 1.
        if before.balances("want", "vault") <= 1:
            return

        assert after.balances("want", "vault") <= before.balances("want", "vault")

        # All want should be in pool OR sitting in strategy, not a mix
        assert (
            after.get("strategy.balanceOfWant") == 0
            and after.get("strategy.estimatedTotalAssets")
            > before.get("strategy.estimatedTotalAssets")
        ) or (
            after.get("strategy.balanceOfWant") > before.get("strategy.balanceOfWant")
            and after.get("strategy.estimatedTotalAssets") == 0
        )

        assert after.get("strategy.balanceOf") > before.get("strategy.balanceOf")
        assert after.balances("want", "user") == before.balances("want", "user")

        self.hook_after_earn(before, after, params)

    def confirm_withdraw(self, before, after, params, tx):
        """
        Withdraw Should;
        - Decrease the totalSupply() of Vault tokens
        - Decrease the balanceOf() Vault tokens for the user based on withdrawAmount and pricePerShare
        - Decrease the balanceOf() want in the Strategy
        - Decrease the balance() tracked for want in the Strategy
        - Decrease the available() if it is not zero
        """
        ppfs = before.get("vault.pricePerShare")

        console.print("=== Compare Withdraw ===")
        self.manager.printCompare(before, after)

        if params["amount"] == 0:
            assert after.get("vault.totalSupply") == before.get("vault.totalSupply")
            # Decrease the Vault tokens for the user based on withdrawAmount and pricePerShare
            assert after.balances("vault", "user") == before.balances("vault", "user")
            return

        # Decrease the totalSupply of Vault tokens
        assert after.get("vault.totalSupply") < before.get("vault.totalSupply")

        # Decrease the Vault tokens for the user based on withdrawAmount and pricePerShare
        assert after.balances("vault", "user") < before.balances("vault", "user")

        # Decrease the want in the Vault, if there was idle want
        if before.balances("want", "vault") > 0:
            assert after.balances("want", "vault") < before.balances("want", "vault")

        # Want in the strategy should be decreased, if idle in vault is insufficient to cover withdrawal
        if params["amount"] > before.balances("want", "vault"):
            # Adjust amount based on total balance x total supply
            # Division in python is not accurate, use Decimal package to ensure division is consistent w/ division inside of EVM
            expectedWithdraw = Decimal(
                params["amount"] * before.get("vault.pricePerShare")
            ) / Decimal(10 ** before.get("vault.decimals"))
            
            # Withdraw from idle in vault first
            expectedWithdraw -= before.balances("want", "vault")
            # First we attempt to withdraw from idle want in strategy
            if expectedWithdraw > before.balances("want", "strategy"):
                # If insufficient, we then attempt to withdraw from activities (balance of pool)
                # Just ensure that we have enough in the pool balance to satisfy the request
                expectedWithdraw -= before.balances("want", "strategy")
                assert expectedWithdraw <= before.get("strategy.estimatedTotalAssets")

                assert approx(
                    before.get("strategy.estimatedTotalAssets"),
                    after.get("strategy.estimatedTotalAssets") + expectedWithdraw,
                    1,
                )

        # The total want between the strategy and vault should be less after than before
        # if there was previous want in strategy or vault (sometimes we withdraw entire
        # balance from the strategy pool) which we check above.
        if (
            before.balances("want", "strategy") > 0
            or before.balances("want", "vault") > 0
        ):
            assert after.balances("want", "strategy") + after.balances(
                "want", "vault"
            ) < before.balances("want", "strategy") + before.balances("want", "vault")

        ## NOTE: there are no fees on withdrawal

        self.hook_after_confirm_withdraw(before, after, params)

    def confirm_deposit(self, before, after, params):
        """
        Deposit Should;
        - Increase the totalSupply() of Vault tokens
        - Increase the balanceOf() Vault tokens for the user based on depositAmount / pricePerShare
        - Increase the balanceOf() want in the Vault by depositAmount
        - Decrease the balanceOf() want of the user by depositAmount
        """

        ppfs = before.get("vault.pricePerShare")
        console.print("=== Compare Deposit ===")
        self.manager.printCompare(before, after)

        ## NOTE: This breaks when you have different decimals for shares
        expected_shares = Decimal(params["amount"] * Wei("1 ether")) / Decimal(ppfs)
        if params.get("expected_shares") is not None:
            expected_shares = params["expected_shares"]

        # Increase the totalSupply() of Vault tokens
        assert approx(
            after.get("vault.totalSupply"),
            before.get("vault.totalSupply") + expected_shares,
            1,
        )

        # Increase the balanceOf() want in the Vault by depositAmount
        assert approx(
            after.balances("want", "vault"),
            before.balances("want", "vault") + params["amount"],
            1,
        )

        # Decrease the balanceOf() want of the user by depositAmount
        assert approx(
            after.balances("want", "user"),
            before.balances("want", "user") - params["amount"],
            1,
        )

        # Increase the balanceOf() Vault tokens for the user based on depositAmount / pricePerShare
        assert approx(
            after.balances("vault", "user"),
            before.balances("vault", "user") + expected_shares,
            1,
        )
        self.hook_after_confirm_deposit(before, after, params)

    # ===== Strategies must implement =====
    def hook_after_confirm_withdraw(self, before, after, params):
        """
            Specifies extra check for ordinary operation on withdrawal
            Use this to verify that balances in the get_strategy_destinations are properly set
        """
        assert False

    def hook_after_confirm_deposit(self, before, after, params):
        """
            Specifies extra check for ordinary operation on deposit
            Use this to verify that balances in the get_strategy_destinations are properly set
        """
        assert False

    def hook_after_earn(self, before, after, params):
        """
            Specifies extra check for ordinary operation on earn
            Use this to verify that balances in the get_strategy_destinations are properly set
        """
        assert False


    def confirm_harvest(self, before, after, tx):
        ## TODO: Harvest should check for Deposit, it then should check for profit or loss
        ## If the strat is in emergency, it should do a different check as well
        """
            Verfies that the Harvest produced yield and fees
        """
        console.print("=== Compare Harvest ===")
        self.manager.printCompare(before, after)
        self.confirm_harvest_state(before, after, tx)

        valueGained = after.get("vault.pricePerShare") > before.get(
            "vault.pricePerShare"
        )

        # # Strategist should earn if fee is enabled and value was generated
        # if before.get("strategy.performanceFeeStrategist") > 0 and valueGained:
        #     assert after.balances("want", "strategist") > before.balances(
        #         "want", "strategist"
        #     )

        # # Strategist should earn if fee is enabled and value was generated
        # if before.get("strategy.performanceFeeGovernance") > 0 and valueGained:
        #     assert after.balances("want", "governanceRewards") > before.balances(
        #         "want", "governanceRewards"
        #     )

    def confirm_tend(self, before, after, tx):
        """
        Tend Should;
        - Increase the number of staked tended tokens in the strategy-specific mechanism
        - Reduce the number of tended tokens in the Strategy to zero

        (Strategy Must Implement)
        """
        assert False

    def get_strategy_destinations(self):
        """
        Track balances for all strategy implementations
        (Strategy Must Implement)
        """
        assert False