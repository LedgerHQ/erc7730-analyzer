# flake8: noqa
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator


class FormatParams(BaseModel):
    model_config = ConfigDict(extra="forbid", exclude_none=True)

    # tokenAmount params
    tokenPath: Optional[str] = None

    # addressName params
    types: Optional[List[str]] = None
    sources: Optional[List[str]] = None

    # unit params
    decimals: Optional[int] = None
    base: Optional[str] = None
    prefix: Optional[bool] = None

    # date params
    encoding: Optional[str] = None

    # nftName params
    collectionPath: Optional[str] = None

    # AI notification fields (will be stripped during post-processing)
    ai__canAcceptEth: Optional[bool] = None

class FieldFormat(BaseModel):
    model_config = ConfigDict(extra="forbid", exclude_none=True)

    format: Literal[
        "raw",
        "amount",
        "duration",
        "tokenAmount",
        "nftName",
        "addressName",
        "date",
        "unit",
    ] = Field(
        ...,
        title="Format Type",
        description="The type of format. Raw is the default format, amount is a special case for amounts.",
    )
    label: str = Field(
        ...,
        title="Field Label",
        description="The label displayed in front of the formatted value.",
    )
    path: str = Field(..., description="Path to the field in the ABI data.")

    # Format-specific parameters as per ERC-7730 specification
    params: Optional[FormatParams] = Field(
        default=None,
        title="Format Parameters",
        description="Format-specific parameters (tokenPath, types, sources, decimals, etc.)",
    )

    # AI notification field (will be stripped during post-processing)
    ai__cannotDetermineTokenPath: Optional[bool] = None


class FunctionFormat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        alias="$id",
        description="Function identifier/name"
    )

    intent: str = Field(
        description="The intent of the function, e.g., 'transfer', 'approve', etc."
    )

    fields: list[FieldFormat] = Field(
        description="A set of field formats used to group whole definitions for structures for instance."
    )

    required: list[str] = Field(
        description="Required fields that are relevant for the user to see. A field is a path to the field in the ABI of the contract."
    )
    excluded: list[str] = Field(
        description="Excluded fields that are not relevant for the user to see. A field is a path to the field in the ABI of the contract."
    )

