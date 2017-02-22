# Tim Cornwell <realtimcornwell@gmail.com>
#
"""
Definition of structures needed by the function interface. These are mostly
subclasses of astropy classes.
"""

import collections

from astropy.coordinates import SkyCoord
from astropy.wcs.utils import skycoord_to_pixel, pixel_to_skycoord

from arl.data.data_models import *
from arl.data.parameters import *

from astropy.convolution import Gaussian2DKernel, Box2DKernel
from astropy.stats import gaussian_fwhm_to_sigma
import astropy.units as u
from photutils import segmentation

log = logging.getLogger(__name__)

def create_skycomponent(direction: SkyCoord, flux: numpy.array, frequency: numpy.array, shape: str = 'Point',
                        param: dict = None, name: str = ''):
    """ A single Skycomponent with direction, flux, shape, and params for the shape

    :param param:
    :param direction:
    :param flux:
    :param frequency:
    :param shape: 'Point' or 'Gaussian'
    :param name:
    :returns: Skycomponent
    """
    return Skycomponent(
        direction = direction,
        frequency = frequency,
        name = name,
        flux = numpy.array(flux),
        shape = shape,
        params = param
        )

def find_nearest_component(home, comps):
    """ Find nearest component to a given direction
    :param home: Home direction
    :param comps: list of skycomponents
    :return: nearest component
    """
    sep = 2 * numpy.pi
    best = None
    for comp in comps:
        thissep = comp.direction.separation(home).rad
        if thissep < sep:
            sep = thissep
            best = comp
    return best
 
def find_skycomponents(im: Image, fwhm=1.0, threshold=10.0, npixels=5):
    """ Find gaussian components in Image above a certain threshold as Skycomponent

    :param fwhm: Full width half maximum of gaussian
    :param threshold: Threshold for component detection. Default: 10 standard deviations over median.
    :param im: Image to be searched
    :param params:
    :returns: list of sky components
    """

    log.info("find_skycomponents: Finding components in Image by segmentation")

    # We use photutils segmentation - this first segments the image
    # into pieces that are thought to contain individual sources, then
    # identifies the concrete source properties. Having these two
    # steps makes it straightforward to extract polarisation and
    # spectral information.

    # Make filter kernel
    sigma = fwhm * gaussian_fwhm_to_sigma
    kernel = Gaussian2DKernel(sigma, x_size=int(1.5*fwhm), y_size=int(1.5*fwhm))
    kernel.normalize()
    
    # Segment the sum of the entire image cube
    image_sum = numpy.sum(im.data, axis=(0,1))
    segments = segmentation.detect_sources(image_sum, threshold, npixels=npixels, filter_kernel=kernel)
    log.info("find_skycomponents: Identified %d segments" % segments.nlabels)

    # Now get source properties for all polarisations and frequencies
    comp_tbl = [ [ segmentation.source_properties(im.data[chan, pol], segments,
                                                  filter_kernel=kernel, wcs=im.wcs)
                   for pol in range(im.npol) ]
                 for chan in range(im.nchan) ]
    def comp_prop(comp,prop_name):
        return [ [ comp_tbl[chan][pol][comp][prop_name]
                   for pol in range(im.npol) ]
                 for chan in range(im.nchan) ]

    # Generate components
    comps = []
    for segment in range(segments.nlabels):

        # Get flux and position. Astropy's quantities make this
        # unecesarily complicated.
        flux = numpy.array(comp_prop(segment, "max_value"))
        # These values seem inconsistent with the xcentroid, and ycentroid values
        # ras = u.Quantity(list(map(u.Quantity,
        #         comp_prop(segment, "ra_icrs_centroid"))))
        # decs = u.Quantity(list(map(u.Quantity,
        #         comp_prop(segment, "dec_icrs_centroid"))))
        xs = u.Quantity(list(map(u.Quantity,
                comp_prop(segment, "xcentroid"))))
        ys = u.Quantity(list(map(u.Quantity,
                comp_prop(segment, "ycentroid"))))
        
        sc = pixel_to_skycoord(xs, ys, im.wcs, 1)
        ras = sc.ra
        decs = sc.dec

        # Remove NaNs from RA/DEC (happens if there is no flux in that
        # polarsiation/channel)
        # ras[numpy.isnan(ras)] = 0.0
        # decs[numpy.isnan(decs)] = 0.0

        # Determine "true" position by weighting
        flux_sum = numpy.sum(flux)
        ra = numpy.sum(flux * ras) / flux_sum
        dec = numpy.sum(flux * decs) / flux_sum
        xs = numpy.sum(flux * xs) / flux_sum
        ys = numpy.sum(flux * ys) / flux_sum

        # Add component
        comps.append(Skycomponent(
            direction = SkyCoord(ra=ra, dec=dec),
            frequency = im.frequency,
            name = "Segment %d" % segment,
            flux = flux,
            shape = 'Point',
            params = {'xpixel':xs, 'ypixel':ys} # Table has lots of data, could add more in future
            ))

    return comps


def insert_skycomponent(im: Image, sc: Skycomponent, insert_method = ''):
    """ Insert a Skycomponet into an image

    :param params:
    :param im:
    :param sc: SkyComponent or list of SkyComponents
    :returns: image

    """

    if not isinstance(sc, collections.Iterable):
        sc = [sc]

    for comp in sc:

        assert comp.shape == 'Point', "Cannot handle shape %s"% comp.shape
    
        if insert_method == "Lanczos":
            pixloc = skycoord_to_pixel(comp.direction, im.wcs, 0, 'wcs')
            log.debug("insert_skycomponent: Performing Lanczos interpolation of flux %s at [%.2f, %.2f] (0 rel) " %
                     (str(comp.flux), pixloc[1], pixloc[0]))
            _L2D(im.data, pixloc[1], pixloc[0], comp.flux)
        else:
            pixloc = numpy.round(skycoord_to_pixel(comp.direction, im.wcs, 1, 'wcs')).astype('int')
            x, y = pixloc[0], pixloc[1]
            log.debug("insert_skycomponent: Inserting point flux %s at [%d, %d] (0 rel) " % (str(comp.flux), x, y))
            im.data[:, :, y, x] += comp.flux
       
    return im



def create_skymodel_from_image(im: Image):
    """ Create a skymodel from an image or image
    
    :param im:
    :returns: Skymodel
    """
    sm = Skymodel()
    sm.images.append(im)
    return sm


def _L2D(im, x, y, flux, a = 7):
    """Perform Lanczos interpolation onto a grid
    
    """
    
    nchan, npol, ny, nx = im.shape
    a=int(a)
    intx = int(numpy.floor(x))
    inty = int(numpy.floor(y))
    fracx = x - intx
    fracy = y - inty
    gridx = numpy.arange(-a, a)
    gridy = numpy.arange(-a, a)

    insert = numpy.zeros([2 * a + 1, 2 * a + 1])
    for iy in gridy:
        insert[iy, gridx + a] = _L(gridx + fracx) * _L(iy + fracy)
    insertsum = numpy.sum(insert)
    assert insertsum > 0, "Sum of interpolation coefficients %g" % insertsum
    insert = insert / insertsum

    for chan in range(nchan):
        for pol in range(npol):
            for iy in gridy:
                im[chan, pol, iy + inty, gridx + intx] += flux[chan,pol] * insert[iy,gridx+a]
            
    return im
    

def _sinc(x):
    s = numpy.zeros_like(x)
    s[x != 0.0] = numpy.sin(numpy.pi*x[x != 0.0])/(numpy.pi*x[x != 0.0])
    return s


def _L(x, a = 5):
    L = _sinc(x) * _sinc(x/a)
    return L
