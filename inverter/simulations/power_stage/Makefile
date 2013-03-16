irf_spice.zip:
	wget http://www.irf.com/product-info/models/spice/spice.zip -O $@

#irfp4668.spi:

%.spi: irf_spice.zip
	unzip $< $@

%.net: %.sch
	gnetlist -g spice -o $@ $<
