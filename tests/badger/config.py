## SET These Variables up for the testing suite
WANT = "0x6b175474e89094c44da98b954eedeac495271d0f" ## Dai
LP_COMPONENT = "0x028171bca77440897b824ca71d1c56cac55b68a3" ## aDAI
REWARD_TOKEN = "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9" ## AAVE Token

PROTECTED_TOKENS = [WANT, LP_COMPONENT, REWARD_TOKEN]
## Fees in Basis Points
DEFAULT_GOV_PERFORMANCE_FEE = 1000 ## TODO: Add to Vault.initialize
DEFAULT_PERFORMANCE_FEE = 1000
DEFAULT_WITHDRAWAL_FEE = 75 ## TODO: Add to Vault setWithdrawalFee
BADGER_DEV_MULTISIG = ""