from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status


def parse_object_id(value: str, field_name: str = "id") -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field_name}")
