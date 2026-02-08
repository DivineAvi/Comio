"""Base schemas with common fields used across all resources."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base for all response schemas.

    ConfigDict settings:
    - from_attributes=True: allows creating schemas from SQLAlchemy model objects.
      Without this, Pydantic can't read data from model.email, model.name, etc.
      Example: UserResponse.model_validate(user_db_object)
    """

    model_config = ConfigDict(from_attributes=True)


class BaseResponse(BaseSchema):
    """Base response with common fields that every resource has."""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
