"""Seal the IOB candidate only after all 13 physical input ILOGIC sites pass."""
from package_saturation import main
if __name__=='__main__':main(require_iob=True)
