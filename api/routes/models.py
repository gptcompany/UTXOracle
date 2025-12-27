"""
API routes for Custom Price Models Framework (spec-036 US6)

Endpoints:
- GET /models - List all available models
- GET /models/{name}/predict - Get prediction from a model
- POST /models/ensemble - Create and predict with ensemble
- GET /models/backtest/{name} - Run backtest on a model
- GET /models/compare - Compare multiple models
"""

from datetime import date
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from api.models.model_framework import (
    BacktestResultResponse,
    EnsembleCreateRequest,
    ModelComparisonResponse,
    ModelInfoResponse,
    ModelPredictionResponse,
)
from scripts.models import ModelRegistry
from scripts.models.backtest.model_backtester import ModelBacktester
from scripts.models.ensemble import EnsembleConfig, EnsembleModel

router = APIRouter(prefix="/models", tags=["models"])


def _name_to_slug(name: str) -> str:
    """Convert model name to URL slug."""
    return name.lower().replace(" ", "-").replace("_", "-")


def _slug_to_name(slug: str) -> str | None:
    """Convert URL slug to model name."""
    # Try to find matching model
    for model_name in ModelRegistry.list_models():
        if _name_to_slug(model_name) == slug.lower():
            return model_name
    return None


def _get_sample_prices() -> pd.Series:
    """Get sample price data for backtesting."""
    # Generate synthetic historical data for demonstration
    # In production, this would load from DuckDB
    dates = pd.date_range(start="2020-01-01", periods=500, freq="D")
    # Simulated price growth with some volatility
    import numpy as np

    np.random.seed(42)
    prices = 10000 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, len(dates))))
    return pd.Series(prices, index=dates)


@router.get("", response_model=list[ModelInfoResponse])
async def list_models() -> list[ModelInfoResponse]:
    """List all available price models."""
    models = []

    for name in ModelRegistry.list_models():
        model = ModelRegistry.create(name)
        models.append(
            ModelInfoResponse(
                name=model.name,
                description=model.description,
                required_data=model.required_data,
                is_fitted=model.is_fitted(),
            )
        )

    return models


@router.get("/{name}/predict", response_model=ModelPredictionResponse)
async def get_model_prediction(
    name: str,
    target_date: Annotated[
        date | None, Query(alias="date", description="Target date for prediction")
    ] = None,
    current_price: Annotated[
        float | None, Query(description="Current price for deviation")
    ] = None,
) -> ModelPredictionResponse:
    """Get price prediction from a specific model."""
    model_name = _slug_to_name(name)

    if model_name is None:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")

    model = ModelRegistry.create(model_name)

    if target_date is None:
        target_date = date.today()

    try:
        prediction = model.predict(target_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e!s}") from e

    return ModelPredictionResponse(
        model_name=prediction.model_name,
        date=prediction.date,
        predicted_price=prediction.predicted_price,
        confidence_interval={
            "lower": prediction.confidence_interval[0],
            "upper": prediction.confidence_interval[1],
        },
        confidence_level=prediction.confidence_level,
        metadata=prediction.metadata,
    )


@router.post("/ensemble", response_model=ModelPredictionResponse)
async def create_ensemble(request: EnsembleCreateRequest) -> ModelPredictionResponse:
    """Create and predict with an ensemble model."""
    # Map slugs to model names
    model_names = []
    for model_slug in request.models:
        model_name = _slug_to_name(model_slug)
        if model_name is None:
            # Try using the slug as-is (might be actual name)
            if model_slug in ModelRegistry.list_models():
                model_name = model_slug
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown model: {model_slug}",
                )
        model_names.append(model_name)

    try:
        config = EnsembleConfig(
            models=model_names,
            weights=request.weights,
            aggregation=request.aggregation,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ensemble = EnsembleModel(config)

    target_date = request.date or date.today()

    try:
        prediction = ensemble.predict(target_date)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Ensemble prediction failed: {e!s}"
        ) from e

    return ModelPredictionResponse(
        model_name=prediction.model_name,
        date=prediction.date,
        predicted_price=prediction.predicted_price,
        confidence_interval={
            "lower": prediction.confidence_interval[0],
            "upper": prediction.confidence_interval[1],
        },
        confidence_level=prediction.confidence_level,
        metadata=prediction.metadata,
    )


@router.get("/backtest/{name}", response_model=BacktestResultResponse)
async def run_backtest(
    name: str,
    start_date: Annotated[date | None, Query(description="Backtest start")] = None,
    end_date: Annotated[date | None, Query(description="Backtest end")] = None,
    train_pct: Annotated[
        float, Query(ge=0.1, le=0.9, description="Training data fraction")
    ] = 0.7,
) -> BacktestResultResponse:
    """Run backtest on a specific model."""
    model_name = _slug_to_name(name)

    if model_name is None:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")

    model = ModelRegistry.create(model_name)
    backtester = ModelBacktester(train_pct=train_pct)

    # Get price data
    prices = _get_sample_prices()

    # Filter by date range if provided
    if start_date:
        prices = prices[prices.index >= pd.Timestamp(start_date)]
    if end_date:
        prices = prices[prices.index <= pd.Timestamp(end_date)]

    if len(prices) < 10:
        raise HTTPException(
            status_code=400,
            detail="Insufficient data for backtesting",
        )

    try:
        result = backtester.run(model, prices)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e!s}") from e

    return BacktestResultResponse(
        model_name=result.model_name,
        start_date=result.start_date,
        end_date=result.end_date,
        predictions=result.predictions,
        metrics={
            "mae": result.mae,
            "mape": result.mape,
            "rmse": result.rmse,
            "direction_accuracy": result.direction_accuracy,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
        },
    )


@router.get("/compare", response_model=ModelComparisonResponse)
async def compare_models(
    models: Annotated[list[str], Query(description="Models to compare")],
    start_date: Annotated[date | None, Query(description="Backtest start")] = None,
    end_date: Annotated[date | None, Query(description="Backtest end")] = None,
) -> ModelComparisonResponse:
    """Compare multiple models on same data."""
    # Map slugs to model names and create instances
    model_instances = []
    model_names = []

    for model_slug in models:
        model_name = _slug_to_name(model_slug)
        if model_name is None:
            # Try using the slug as-is
            if model_slug in ModelRegistry.list_models():
                model_name = model_slug
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown model: {model_slug}",
                )
        model_instances.append(ModelRegistry.create(model_name))
        model_names.append(model_name)

    backtester = ModelBacktester()

    # Get price data
    prices = _get_sample_prices()

    if start_date:
        prices = prices[prices.index >= pd.Timestamp(start_date)]
    if end_date:
        prices = prices[prices.index <= pd.Timestamp(end_date)]

    if len(prices) < 10:
        raise HTTPException(
            status_code=400,
            detail="Insufficient data for comparison",
        )

    # Run backtests
    results = []
    for model in model_instances:
        try:
            result = backtester.run(model, prices)
            results.append(result)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Backtest failed for {model.name}: {e!s}",
            ) from e

    # Sort by MAPE
    results.sort(key=lambda r: r.mape)

    ranking = [r.model_name for r in results]
    best_model = ranking[0] if ranking else ""

    result_responses = [
        BacktestResultResponse(
            model_name=r.model_name,
            start_date=r.start_date,
            end_date=r.end_date,
            predictions=r.predictions,
            metrics={
                "mae": r.mae,
                "mape": r.mape,
                "rmse": r.rmse,
                "direction_accuracy": r.direction_accuracy,
                "sharpe_ratio": r.sharpe_ratio,
                "max_drawdown": r.max_drawdown,
            },
        )
        for r in results
    ]

    return ModelComparisonResponse(
        models=model_names,
        ranking=ranking,
        best_model=best_model,
        results=result_responses,
    )
