#!/usr/bin/env python3
"""
Nanobot Factory - FiftyOne Integration Module
Real integration with FiftyOne open-source dataset management tool

FiftyOne provides:
- Powerful data visualization
- Sample management with rich metadata
- Dataset statistics and analytics
- Embeddings and similarity search
- Evaluation and quality assessment
- Plugin system for extensibility

@author MiniMax Agent
@date 2026-02-28
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import FiftyOne
try:
    import fiftyone as fo
    import fiftyone.zoo as foz
    import fiftyone.core as foc
    import fiftyone.core.view as fov
    from fiftyone.core.collections import SampleCollection
    from fiftyone.core.sample import Sample
    HAS_FIFTYONE = True
except ImportError:
    HAS_FIFTYONE = False
    logger.warning("FiftyOne not installed. Install with: pip install fiftyone")


@dataclass
class NanobotFiftyOneConfig:
    """Configuration for FiftyOne integration"""
    dataset_dir: str = "./fiftyone_datasets"
    default_num_workers: int = 4
    batch_size: int = 32
    compute_embeddings: bool = True
    default_embedding_model: str = "resnet50-imagenet-torch"


class FiftyOneIntegration:
    """
    FiftyOne Integration for Nanobot Factory

    Provides real dataset management capabilities:
    - Dataset creation and management
    - Sample CRUD operations
    - Rich metadata and tags
    - Quality evaluation
    - Similarity search
    - Export/Import
    """

    def __init__(self, config: NanobotFiftyOneConfig = None):
        self.config = config or NanobotFiftyOneConfig()

        if not HAS_FIFTYONE:
            raise ImportError("FiftyOne is not installed. Run: pip install fiftyone")

        # Ensure dataset directory exists
        os.makedirs(self.config.dataset_dir, exist_ok=True)

        # Configure FiftyOne
        fo.config.dataset_dir = self.config.dataset_dir
        fo.config.default_num_workers = self.config.default_num_workers

        logger.info("FiftyOne integration initialized")

    def create_dataset(
        self,
        name: str,
        description: str = "",
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Create a new FiftyOne dataset

        Args:
            name: Dataset name
            description: Dataset description
            metadata: Additional metadata

        Returns:
            Dataset ID
        """
        try:
            # Check if dataset already exists
            existing = fo.load_dataset(name)
            if existing:
                logger.warning(f"Dataset '{name}' already exists, returning existing")
                return existing.name

            # Create new dataset
            dataset = fo.Dataset(
                name=name,
                description=description,
                metadata=metadata or {}
            )

            dataset.save()
            logger.info(f"Created FiftyOne dataset: {name}")
            return dataset.name

        except Exception as e:
            logger.error(f"Failed to create dataset: {e}")
            raise

    def delete_dataset(self, name: str, force: bool = False) -> bool:
        """
        Delete a FiftyOne dataset

        Args:
            name: Dataset name
            force: Force deletion without confirmation

        Returns:
            Success status
        """
        try:
            dataset = fo.load_dataset(name)
            if not dataset:
                logger.warning(f"Dataset '{name}' not found")
                return False

            dataset.delete()
            logger.info(f"Deleted FiftyOne dataset: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete dataset: {e}")
            return False

    def list_datasets(self) -> List[Dict[str, Any]]:
        """
        List all FiftyOne datasets

        Returns:
            List of dataset info
        """
        try:
            datasets = fo.list_datasets()
            result = []

            for name in datasets:
                dataset = fo.load_dataset(name)
                result.append({
                    "name": dataset.name,
                    "description": dataset.description,
                    "sample_count": dataset.num_samples,
                    "created_at": dataset.created_at.isoformat() if hasattr(dataset, 'created_at') else None,
                    "last_modified": dataset.last_modified.isoformat() if hasattr(dataset, 'last_modified') else None,
                })

            return result

        except Exception as e:
            logger.error(f"Failed to list datasets: {e}")
            return []

    def add_sample(
        self,
        dataset_name: str,
        filepath: str,
        metadata: Dict[str, Any] = None,
        tags: List[str] = None,
        quality_score: float = None,
        aesthetic_score: float = None,
        **kwargs
    ) -> str:
        """
        Add a sample to a dataset

        Args:
            dataset_name: Dataset name
            filepath: Path to media file
            metadata: Additional metadata
            tags: Tags for the sample
            quality_score: Quality score (0-1)
            aesthetic_score: Aesthetic score (0-1)
            **kwargs: Additional fields

        Returns:
            Sample ID
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                raise ValueError(f"Dataset '{dataset_name}' not found")

            # Create sample
            sample = Sample(filepath=filepath)

            # Add metadata
            if metadata:
                for key, value in metadata.items():
                    sample[key] = value

            # Add tags
            if tags:
                sample.tags = tags

            # Add scores
            if quality_score is not None:
                sample["quality_score"] = quality_score

            if aesthetic_score is not None:
                sample["aesthetic_score"] = aesthetic_score

            # Add custom fields
            for key, value in kwargs.items():
                sample[key] = value

            # Add to dataset
            dataset.add_sample(sample)
            dataset.save()

            logger.info(f"Added sample to dataset {dataset_name}: {filepath}")
            return sample.id

        except Exception as e:
            logger.error(f"Failed to add sample: {e}")
            raise

    def add_samples_batch(
        self,
        dataset_name: str,
        samples_data: List[Dict[str, Any]]
    ) -> int:
        """
        Add multiple samples at once

        Args:
            dataset_name: Dataset name
            samples_data: List of sample data

        Returns:
            Number of samples added
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                raise ValueError(f"Dataset '{dataset_name}' not found")

            samples = []
            for data in samples_data:
                filepath = data.get("filepath")
                if not filepath:
                    continue

                sample = Sample(filepath=filepath)

                # Add all fields from data
                for key, value in data.items():
                    if key != "filepath":
                        sample[key] = value

                samples.append(sample)

            dataset.add_samples(samples)
            dataset.save()

            logger.info(f"Added {len(samples)} samples to dataset {dataset_name}")
            return len(samples)

        except Exception as e:
            logger.error(f"Failed to add samples batch: {e}")
            raise

    def get_sample(self, dataset_name: str, sample_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a sample by ID

        Args:
            dataset_name: Dataset name
            sample_id: Sample ID

        Returns:
            Sample data or None
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                return None

            sample = dataset[sample_id]
            if not sample:
                return None

            return self._sample_to_dict(sample)

        except Exception as e:
            logger.error(f"Failed to get sample: {e}")
            return None

    def update_sample(
        self,
        dataset_name: str,
        sample_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update a sample

        Args:
            dataset_name: Dataset name
            sample_id: Sample ID
            updates: Fields to update

        Returns:
            Success status
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                return False

            sample = dataset[sample_id]
            if not sample:
                return False

            # Apply updates
            for key, value in updates.items():
                sample[key] = value

            sample.save()
            dataset.save()

            logger.info(f"Updated sample {sample_id} in dataset {dataset_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to update sample: {e}")
            return False

    def delete_sample(self, dataset_name: str, sample_id: str) -> bool:
        """
        Delete a sample

        Args:
            dataset_name: Dataset name
            sample_id: Sample ID

        Returns:
            Success status
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                return False

            sample = dataset[sample_id]
            if not sample:
                return False

            dataset.delete_sample(sample_id)
            dataset.save()

            logger.info(f"Deleted sample {sample_id} from dataset {dataset_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete sample: {e}")
            return False

    def search_samples(
        self,
        dataset_name: str,
        filters: Dict[str, Any] = None,
        tags: List[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search samples with filters

        Args:
            dataset_name: Dataset name
            filters: Field filters
            tags: Tag filters
            limit: Maximum results

        Returns:
            List of matching samples
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                return []

            # Build view
            view = dataset.view()

            # Apply filters
            if filters:
                for field, value in filters.items():
                    view = view.match({field: value})

            # Apply tag filter
            if tags:
                for tag in tags:
                    view = view.match_tags(tag)

            # Limit results
            if limit:
                view = view.limit(limit)

            # Convert to list
            results = []
            for sample in view:
                results.append(self._sample_to_dict(sample))

            return results

        except Exception as e:
            logger.error(f"Failed to search samples: {e}")
            return []

    def get_dataset_stats(self, dataset_name: str) -> Dict[str, Any]:
        """
        Get dataset statistics

        Args:
            dataset_name: Dataset name

        Returns:
            Statistics dictionary
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                return {}

            # Get basic stats
            stats = {
                "name": dataset.name,
                "description": dataset.description,
                "sample_count": dataset.num_samples,
                "created_at": str(dataset.created_at) if dataset.created_at else None,
                "last_modified": str(dataset.last_modified) if dataset.last_modified else None,
            }

            # Get field stats
            field_stats = {}
            for field_name in dataset.get_field_schema().keys():
                field_stats[field_name] = {
                    "type": str(type(dataset.get_field(field_name)).__name__)
                }
            stats["fields"] = field_stats

            # Get tag distribution
            tags = dataset.distinct("tags")
            tag_counts = {}
            for tag in tags:
                count = len(dataset.match_tags(tag))
                tag_counts[tag] = count
            stats["tags"] = tag_counts

            # Get class distribution (if exists)
            if "label" in dataset.get_field_schema():
                labels = dataset.distinct("label")
                label_counts = {}
                for label in labels:
                    count = len(dataset.match({"label": label}))
                    label_counts[label] = count
                stats["labels"] = label_counts

            return stats

        except Exception as e:
            logger.error(f"Failed to get dataset stats: {e}")
            return {}

    def compute_embeddings(
        self,
        dataset_name: str,
        model_name: str = None,
        embeddings_field: str = "embedding",
        batch_size: int = None
    ) -> bool:
        """
        Compute embeddings for all samples

        Args:
            dataset_name: Dataset name
            model_name: Model name (default from config)
            embeddings_field: Field to store embeddings
            batch_size: Batch size

        Returns:
            Success status
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                return False

            model_name = model_name or self.config.default_embedding_model
            batch_size = batch_size or self.config.batch_size

            # Compute embeddings
            embeddings = foz.compute_embeddings(
                dataset,
                model=model_name,
                embeddings_field=embeddings_field,
                batch_size=batch_size
            )

            dataset.save()

            logger.info(f"Computed embeddings for dataset {dataset_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to compute embeddings: {e}")
            return False

    def find_similar(
        self,
        dataset_name: str,
        sample_id: str,
        embeddings_field: str = "embedding",
        num_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find similar samples using embeddings

        Args:
            dataset_name: Dataset name
            sample_id: Sample ID to find similar to
            embeddings_field: Embeddings field
            num_results: Number of results

        Returns:
            List of similar samples
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                return []

            sample = dataset[sample_id]
            if not sample:
                return []

            # Find similar
            similar = dataset.find_similar(
                sample_id,
                embeddings_field=embeddings_field,
                num_results=num_results
            )

            results = []
            for s in similar:
                results.append(self._sample_to_dict(s))

            return results

        except Exception as e:
            logger.error(f"Failed to find similar: {e}")
            return []

    def evaluate_quality(
        self,
        dataset_name: str,
        label_field: str = "quality",
        predicted_field: str = "predicted_quality"
    ) -> Dict[str, Any]:
        """
        Evaluate quality predictions

        Args:
            dataset_name: Dataset name
            label_field: Ground truth field
            predicted_field: Predicted field

        Returns:
            Evaluation results
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                return {}

            # Check if fields exist
            if label_field not in dataset.get_field_schema():
                logger.warning(f"Label field '{label_field}' not found")
                return {}

            # Compute evaluation
            eval_result = fo.evaluate_classifications(
                dataset,
                pred_field=predicted_field,
                gt_field=label_field
            )

            # Get metrics
            metrics = {
                "accuracy": eval_result.accuracy(),
                "precision": eval_result.precision(),
                "recall": eval_result.recall(),
                "f1_score": eval_result.f1(),
            }

            return metrics

        except Exception as e:
            logger.error(f"Failed to evaluate quality: {e}")
            return {}

    def export_dataset(
        self,
        dataset_name: str,
        export_dir: str,
        export_format: str = "csv",
        split: bool = False
    ) -> bool:
        """
        Export dataset

        Args:
            dataset_name: Dataset name
            export_dir: Export directory
            export_format: Format (csv, json, coco, yolo, etc.)
            split: Whether to split by train/val/test

        Returns:
            Success status
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                return False

            # Export
            dataset.export(
                export_dir=export_dir,
                export_format=export_format,
                split=split
            )

            logger.info(f"Exported dataset {dataset_name} to {export_dir}")
            return True

        except Exception as e:
            logger.error(f"Failed to export dataset: {e}")
            return False

    def import_from_directory(
        self,
        dataset_name: str,
        dataset_dir: str,
        import_format: str = "video"
    ) -> int:
        """
        Import dataset from directory

        Args:
            dataset_name: Target dataset name
            dataset_dir: Source directory
            import_format: Format type

        Returns:
            Number of samples imported
        """
        try:
            # Create or load dataset
            try:
                dataset = fo.load_dataset(dataset_name)
            except (fo.DatasetNotFoundError, ValueError):
                dataset = fo.Dataset(dataset_name)

            # Import
            dataset.add_dir(
                dataset_dir=dataset_dir,
                dataset_type=fo.types.import_format(import_format)
            )

            dataset.save()

            count = dataset.num_samples
            logger.info(f"Imported {count} samples to dataset {dataset_name}")
            return count

        except Exception as e:
            logger.error(f"Failed to import dataset: {e}")
            return 0

    def create_view(
        self,
        dataset_name: str,
        view_config: Dict[str, Any]
    ) -> str:
        """
        Create a saved view

        Args:
            dataset_name: Dataset name
            view_config: View configuration

        Returns:
            View name
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                raise ValueError(f"Dataset '{dataset_name}' not found")

            # Build view from config
            view = dataset.view()

            # Apply stages from config
            stages = view_config.get("stages", [])
            for stage in stages:
                stage_type = stage.get("type")
                params = stage.get("params", {})

                if stage_type == "filter":
                    view = view.match(params.get("filter", {}))
                elif stage_type == "tags":
                    view = view.match_tags(params.get("tags", []))
                elif stage_type == "limit":
                    view = view.limit(params.get("limit", 100))
                elif stage_type == "skip":
                    view = view.skip(params.get("skip", 0))
                elif stage_type == "sort_by":
                    view = view.sort_by(
                        params.get("field", "created_at"),
                        reverse=params.get("reverse", False)
                    )

            # Save view
            view_name = view_config.get("name", f"view_{datetime.now().timestamp()}")
            dataset.save_view(view_name=view_name, view=view)

            logger.info(f"Created view '{view_name}' in dataset {dataset_name}")
            return view_name

        except Exception as e:
            logger.error(f"Failed to create view: {e}")
            raise

    def get_views(self, dataset_name: str) -> List[Dict[str, Any]]:
        """
        Get saved views

        Args:
            dataset_name: Dataset name

        Returns:
            List of views
        """
        try:
            dataset = fo.load_dataset(dataset_name)
            if not dataset:
                return []

            views = []
            for view in dataset.list_views():
                views.append({
                    "name": view,
                    "num_samples": len(dataset.get_view(view))
                })

            return views

        except Exception as e:
            logger.error(f"Failed to get views: {e}")
            return []

    def _sample_to_dict(self, sample) -> Dict[str, Any]:
        """Convert sample to dictionary"""
        try:
            data = {
                "id": sample.id,
                "filepath": sample.filepath,
                "tags": list(sample.tags) if sample.tags else [],
            }

            # Add all other fields
            for field_name in sample.keys():
                if field_name not in ["id", "filepath", "tags"]:
                    value = sample[field_name]
                    # Handle numpy arrays
                    if hasattr(value, 'tolist'):
                        value = value.tolist()
                    data[field_name] = value

            return data

        except Exception as e:
            logger.error(f"Failed to convert sample to dict: {e}")
            return {}

    def clone_dataset(self, source_name: str, target_name: str) -> str:
        """
        Clone a dataset

        Args:
            source_name: Source dataset name
            target_name: Target dataset name

        Returns:
            New dataset name
        """
        try:
            source = fo.load_dataset(source_name)
            if not source:
                raise ValueError(f"Source dataset '{source_name}' not found")

            # Clone
            target = source.clone(name=target_name)
            target.save()

            logger.info(f"Cloned dataset {source_name} to {target_name}")
            return target.name

        except Exception as e:
            logger.error(f"Failed to clone dataset: {e}")
            raise

    def merge_datasets(
        self,
        source_names: List[str],
        target_name: str,
        fields_map: Dict[str, str] = None
    ) -> str:
        """
        Merge multiple datasets

        Args:
            source_names: Source dataset names
            target_name: Target dataset name
            fields_map: Field mapping

        Returns:
            New dataset name
        """
        try:
            # Load all sources
            sources = []
            for name in source_names:
                ds = fo.load_dataset(name)
                if ds:
                    sources.append(ds)

            if not sources:
                raise ValueError("No valid source datasets")

            # Merge
            merged = sources[0].merge(sources[1:], name=target_name)

            if fields_map:
                # Apply field mapping
                for old_field, new_field in fields_map.items():
                    merged = merged.rename_field(old_field, new_field)

            merged.save()

            logger.info(f"Merged {len(sources)} datasets to {target_name}")
            return merged.name

        except Exception as e:
            logger.error(f"Failed to merge datasets: {e}")
            raise


# Singleton instance
_fiftyone_integration = None

def get_fiftyone_integration(config: NanobotFiftyOneConfig = None) -> FiftyOneIntegration:
    """Get singleton FiftyOne integration instance"""
    global _fiftyone_integration
    if _fiftyone_integration is None:
        _fiftyone_integration = FiftyOneIntegration(config)
    return _fiftyone_integration


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if not HAS_FIFTYONE:
        print("FiftyOne not installed. Run: pip install fiftyone")
        exit(1)

    # Initialize
    foi = FiftyOneIntegration()

    # Create dataset
    dataset_name =foi.create_dataset(
        name="test_dataset",
        description="Test dataset for FiftyOne integration"
    )
    print(f"Created dataset: {dataset_name}")

    # List datasets
    datasets = foi.list_datasets()
    print(f"Available datasets: {datasets}")

    # Get stats
    stats = foi.get_dataset_stats(dataset_name)
    print(f"Dataset stats: {stats}")
