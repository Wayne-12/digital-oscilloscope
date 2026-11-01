"""Rebuild the current ADC IOB design, requiring actual routed ILOGIC placement."""
from build_saturation import main
if __name__=='__main__':main(require_iob=True)
