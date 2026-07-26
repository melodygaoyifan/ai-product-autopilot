# autoproduct dev tasks. `make help` lists targets.
.DEFAULT_GOAL := help
IMAGE := autoproduct-calibrate

.PHONY: help test calibrate calibrate-build calibrate-local

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n", $$1, $$2}'

test: ## Run the full test suite (hermetic; no scanners needed)
	uv run pytest -q

calibrate-build: ## Build the scanner-calibration container image
	docker build -f Dockerfile.calibrate -t $(IMAGE) .

calibrate: calibrate-build ## Calibrate seeded-lane patterns against real scanners (§19 G7)
	docker run --rm -v "$(CURDIR)/.mas:/work/.mas" $(IMAGE)

calibrate-local: ## Run calibration on the host (needs the scanners already installed)
	scripts/calibrate.sh
