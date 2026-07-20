from __future__ import annotations

from warhammer40k_core.core.attachment_eligibility import AttachmentEligibility
from warhammer40k_core.core.datasheet import DatasheetDefinition


def required_attachment_eligibility(
    datasheet: DatasheetDefinition,
    *,
    error_type: type[ValueError],
) -> AttachmentEligibility:
    if type(datasheet) is not DatasheetDefinition:
        raise error_type("Attachment eligibility lookup requires a DatasheetDefinition.")
    eligibilities = datasheet.attachment_eligibilities
    if not eligibilities:
        raise error_type("AttachmentDeclaration source datasheet has no attachment eligibility.")
    if len(eligibilities) != 1:
        raise error_type(
            "AttachmentDeclaration source datasheet must declare exactly one attachment role."
        )
    return eligibilities[0]
