"""The HTTP contract with the LabSense backend (its `src/modules/lab-uploads/app/redactor.ts`).

Boxes are fractions of the page as displayed (rotation applied), from its top-left corner, on
1-based pages. Field names are camelCase on the wire.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

RedactionType = Literal[
    "name",
    "date_of_birth",
    "address",
    "phone",
    "email",
    "id_number",
    "policy_number",
    # A block the user added with `Hide` on the review screen; never returned by /detect.
    "manual",
]

#: A storage key: what the backend gives, e.g. `acc/{account}/{file}`.
Key = Annotated[
    str, StringConstraints(min_length=1, max_length=1024, pattern=r"^[A-Za-z0-9][A-Za-z0-9/_.\-]*$")
]
Fraction = Annotated[float, Field(ge=0, le=1)]
PageNumber = Annotated[int, Field(ge=1)]
PageCount = Annotated[int, Field(ge=1, le=200)]


class Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class Box(Model):
    x0: Fraction
    y0: Fraction
    x1: Fraction
    y1: Fraction

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not (self.x0 < self.x1 and self.y0 < self.y1):
            raise ValueError("a box needs x0 < x1 and y0 < y1")
        return self


class Region(Box):
    page: PageNumber
    type: RedactionType


class Known(Model):
    """The account's known details. Never logged."""

    names: Annotated[list[Annotated[str, StringConstraints(max_length=200)]], Field(max_length=50)] = []
    emails: Annotated[list[Annotated[str, StringConstraints(max_length=320)]], Field(max_length=20)] = []
    birth_years: Annotated[list[Annotated[int, Field(ge=1900, le=2100)]], Field(max_length=50)] = []


class DetectRequest(Model):
    key: Key
    page_count: PageCount
    known: Known = Known()


class DetectResponse(Model):
    regions: list[Region]
    #: Distinct details per type: a name repeated in every page header counts once.
    summary: dict[str, int]
    #: The pages are scans under an OCR text layer, or their text can't be read: the text
    #: can't be trusted, so the backend sends the user to paint over the pages instead.
    scanned: bool


class WordsRequest(Model):
    key: Key
    page_count: PageCount


class Word(Box):
    text: str


class PageWords(Model):
    page: PageNumber
    words: list[Word]


class WordsResponse(Model):
    pages: list[PageWords]


class ApplyRequest(Model):
    key: Key
    regions: Annotated[list[Region], Field(max_length=5000)]
    output_key: Key


class ApplyResponse(Model):
    #: The copy's text was extracted again and none of the hidden details remain.
    verified: bool
    byte_size: int
    sha256: str


class RasterOutput(Model):
    page: PageNumber
    key: Key


class RasterizeRequest(Model):
    key: Key
    regions: Annotated[list[Region], Field(max_length=5000)]
    outputs: Annotated[list[RasterOutput], Field(min_length=1, max_length=200)]


class RasterPage(Model):
    page: PageNumber
    byte_size: int
    sha256: str


class RasterizeResponse(Model):
    pages: list[RasterPage]
