from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=True)
async def health_check():
    return {"status": "ok", "service": "confhub"}
