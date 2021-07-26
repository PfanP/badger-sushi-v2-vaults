from brownie import *
from helpers.constants import MaxUint256


def test_are_you_trying(user, vault, strategy, token, amount, gov):
  """
    Verifies that you set up the Strategy properly
  """
  # Setup
  startingBalance = amount
  
  depositAmount = startingBalance // 2
  assert startingBalance >= depositAmount
  assert startingBalance >= 0
  # End Setup

  # Deposit
  assert token.balanceOf(vault) == 0

  token.approve(vault, MaxUint256, {"from": user})
  vault.deposit(depositAmount, {"from": user})

  available = token.balanceOf(vault)
  assert available > 0 

  ## Load funds in
  strategy.harvest()

  chain.mine(100) # Mine so we get some interest

  ## TEST 1: Does the token get used in any way?
  assert token.balanceOf(vault) == depositAmount - available

  # Did the strategy do something with the asset?
  assert token.balanceOf(strategy) <= depositAmount

  # Use this if it should invest all
  # assert token.balanceOf(strategy) == 0
  