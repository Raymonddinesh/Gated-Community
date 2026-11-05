"""Phase 14 Facility & Asset Management Custom Exceptions."""

from fastapi import HTTPException, status


class FacilityAssetException(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


class FacilityNotFoundError(FacilityAssetException):
    def __init__(self, facility_id: str | None = None):
        detail = f"Facility {facility_id} not found." if facility_id else "Facility not found."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class FacilityAreaNotFoundError(FacilityAssetException):
    def __init__(self, area_id: str | None = None):
        detail = f"Facility Area {area_id} not found." if area_id else "Facility Area not found."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class AssetNotFoundError(FacilityAssetException):
    def __init__(self, asset_id: str | None = None):
        detail = f"Asset {asset_id} not found." if asset_id else "Asset not found."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class AssetCategoryNotFoundError(FacilityAssetException):
    def __init__(self, category_id: str | None = None):
        detail = f"Asset Category {category_id} not found." if category_id else "Asset Category not found."
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class DuplicateCodeError(FacilityAssetException):
    def __init__(self, code_type: str, code_value: str):
        super().__init__(
            detail=f"{code_type} with code '{code_value}' already exists in this society.",
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidStateTransitionError(FacilityAssetException):
    def __init__(self, current_status: str, target_status: str):
        super().__init__(
            detail=f"Invalid status transition from {current_status} to {target_status}.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class FinancialMutationBlockedError(FacilityAssetException):
    def __init__(self, detail: str = "Financial records cannot be mutated by Facility/Asset module."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)
