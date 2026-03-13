Changes
 

Change

Example

Description

String Interpolated Intent



{
  "display": {
    "formats": {
      "transfer(address to,uint256 amount)": {
        "interpolatedIntent": "Send {amount} to {to}"
} } } }
Compact representation in one string of the full intent of the transaction.

Useful mostly for software wallets, HW wallets will be using intents + fields directly.

Add contractName 



{
  "metadata": {
    "contractName": "Uniswap Universal Router"
} }
Official contract name.

Replace Ledger use of “$id” field in the context (that was always supposed to be an internal doc field)

Add tockenTicker 



{
  "display": {
    "formats": {
      "setRewardToken(address token)": {
        "fields": [
          {
            "path": "token",
            "format": "tokenTicker"
          }
        ]
} } } }
Displays an address as a token ticker, when ticker is available

Already supported by the Ethereum app

Add @.chainId



{
  "display": {
    "formats": {
      "bridge(uint256 amount, uint256 targetChain)": {
        "intent": "Bridge",
        "fields": [
          {
            "path": "@.chainId",
            "label": "Source chain"
            "format": "raw"
          }
        ]
} } } }
@.chainId enables accessing the container value containing the source chain ID

Should we also add a chainId formatter?

 

Add $comments



{
  "$comments": "This is an example of a 7730 file."
}
Allows commenting 7730 files themselves

ABI and EIP712 schemas in display.formats keys



{
  "display": {
    "formats": {
      "transfer(address to,uint256 amount)": {
        ...
      }
} } }


{
  "display": {
    "formats": {
      "PermitSingle(address token,address spender,uint256 amount,uint256 expiration,uint256 nonce)
": {
        ...
      }
} } }
No more ABI key or schema key, the reference schema is in the keys names themselves

Array iteration and grouping



{
  "display": {
    "formats": {
      "distribute(address[] recipients,uint256[] percentages)": {
                "intent": "Distribute fees to recipients",
                "interpolatedIntent": "Distribute fees {percentages} to recipients {recipients}",
                "fields": [
                    {
                        "path": "@.value",
                        "label": "Total Distributed Amount",
                        "format": "amount"
                    },
                    {
                        "label": "Recipients and Fees",
                        "iteration": "bundled",
                        "fields": [
                            {
                                "path": "recipients.[]",
                                "label": "Recipients",
                                "format": "addressName",
                                "separator": "Recipient {index}"
                            },
                            {
                                "path": "percentages.[]",
                                "label": "Percentages",
                                "format": "unit",
                                "params": {
                                    "base": "%",
                                    "decimals": 2
                                }
                            }
                        ]
                    }
                ]
            }
  }
}
Specify better how bundled mode works for primitive fields (suggested: repetition)

Three “new” features to study:


Grouping fields based on json array order, labels on groups of fields

Controlling array iteration inside a group using “iteration”

Adding separators between elements of an array

 

ADR required (new grouping descriptor)

Support for maps



{
  "metadata": {
        "maps": {
            "underlyingToken": {
                "keyPath": "@.chainId",
                "values": {
                    "1": "0x0000000000000000000000000000000000deadbeef",
                    "137": "0x0000000000000000000000000000000000feedface",
                    "42161": "0x0000000000000000000000000000000000cafebabe"
                }
            },
            "shareToken": {
                "keyPath": "@.chainId",
                "values": {
                    "1": "0x00000000000000000000000000000000abcdef01",
                    "137": "0x00000000000000000000000000000000abcdef02",
                    "42161": "0x00000000000000000000000000000000abcdef03"
                }
            }
        }
    }
}
How do we specify better the key path (key path is relative to where the maps is used, but global when defined in the metadata section, might require repetition of the map in some cases)?

Do we support multi-dimensional maps?

ADR required (enum like descriptor required)

Constraints on values, remove excluded/required



{
   "display": {
        "formats": {
            "transfer(address to, address referrer, address rfu, uint256 legacy, uint256 fee)": {
                "intent": "Send",
                "interpolatedIntent": "Send {value} to {to}",
                "fields": [
                    {
                        "$id": "To is a critical field always displayed",
                        "path": "to",
                        "label": "To",
                        "format": "addressName",
                        "visible": "always"
                    },
                    {
                        "$id": "Referrer is an optional field displayed only if wallet finds it useful",
                        "path": "referrer",
                        "label": "Referrer",
                        "format": "addressName",
                        "visible": "optional"
                    },
                    {
                        "$id": "RFU is an unused field that should never be displayed",
                        "path": "rfu",
                        "visible": "never"
                    },
                    {
                        "$id": "Legacy is an unused field that must be zero or the Tx is malformed",
                        "path": "legacy",
                        "visible": {
                            "mustBe": [0]
                        }
                    },
                    {
                        "$id": "Fee is an interesting field to display only if non-zero",
                        "path": "fee",
                        "label": "Fee Amount",
                        "format": "amount",
                        "visible": {
                            "ifNotIn": [0]
                        }
                    }
                ]
            }
        }
    }
}
“visible” replaces excluded and required arrays.

Listing all paths of the function in the “fields” becomes mandatory  

ADR required (new TLV in descriptors)

Interoperable Addresses

 

ADR required (new formatter descriptor)

ChainID formatter

 

ADR required (new formatter descriptor)

Remove addressMatcher / legalName / enums URL

 

Unused forms

The following changes are purely informational, or for clarity of the specification:

Remove registry info from ERC

Add versioning

Batch Transaction Support

Common Keywords

Add Trust assumptions

Limits on fields (recommendation)

The following proposals are left for future consideration:

Open Intents Compatibility: OIF address format

I18N Support

Signed Integrity Annotation

Introduce Interfaces


mustBe: [0]


tous les champs doivent être exprimés