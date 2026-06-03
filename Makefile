.PHONY: test demo

test:
	python -m unittest discover -s tests

demo:
	python -m oci_zpr_visibility.cli demo --output-dir out/demo
