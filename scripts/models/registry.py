"""
ModelRegistry for model discovery and instantiation (spec-036 US2)

Provides:
- @ModelRegistry.register decorator for auto-registration
- ModelRegistry.get() to retrieve model class by name
- ModelRegistry.list_models() to enumerate registered models
- ModelRegistry.create() factory method for instantiation
"""

from typing import Any

from scripts.models.base import PriceModel


class ModelRegistry:
    """Registry for PriceModel discovery and instantiation."""

    _models: dict[str, type[PriceModel]] = {}

    @classmethod
    def register(cls, model_class: type[PriceModel]) -> type[PriceModel]:
        """Decorator to register a model class.

        Usage:
            @ModelRegistry.register
            class MyModel(PriceModel):
                @property
                def name(self) -> str:
                    return "My Model"
                ...
        """
        # Create a temporary instance to get the name property value
        try:
            instance = model_class()
            name = instance.name
        except TypeError:
            # Can't instantiate (e.g., still abstract), use class name
            name = model_class.__name__

        cls._models[name] = model_class
        return model_class

    @classmethod
    def get(cls, name: str) -> type[PriceModel]:
        """Get model class by name.

        Args:
            name: Human-readable model name

        Returns:
            Model class

        Raises:
            KeyError: If model not found
        """
        if name not in cls._models:
            raise KeyError(f"Unknown model: {name}")
        return cls._models[name]

    @classmethod
    def list_models(cls) -> list[str]:
        """List all registered model names.

        Returns:
            List of model names
        """
        return list(cls._models.keys())

    @classmethod
    def create(cls, name: str, **config: Any) -> PriceModel:
        """Create model instance by name with optional config.

        Args:
            name: Human-readable model name
            **config: Model-specific configuration kwargs

        Returns:
            Instantiated model

        Raises:
            KeyError: If model not found
        """
        model_class = cls.get(name)
        return model_class(**config)
