import numpy as np
import craystack.vectorans as vrans


def NonUniform(enc_statfun, dec_statfun, precision):
    """
    Codec for symbols which are not uniformly distributed. The statfuns specify
    the following mappings:

        enc_statfun: symbol |-> start, freq
        dec_statfun: cf |-> symbol

    The interval [0, 1) is modelled by the range of integers
    [0, 2 ** precision). The operation performed by enc_statfun is used for
    compressing data and is visualised below for a distribution over a set of
    symbols {a, b, c, d}.

    0                                                         2 ** precision
    |    a              !b!              c              d         |
    |----------|--------------------|---------|-------------------|
               |------ freq --------|
             start

    Calling enc_statfun(b) must return the pair (start, freq), where start is
    the start of the interval representing the symbol b and freq is its width.
    Start and freq must satisfy the following constraints:

        0 <  freq
        0 <= start        <  2 ** precision
        0 <  start + freq <= 2 ** precision

    The value of start is analagous to the cdf of the distribution, evaluated
    at b, while freq is analagous to the pmf evaluated at b.

    The function dec_statfun essentially inverts enc_statfun. It is
    necessary for decompressing data, to recover the original symbol.

    0                                                         2 ** precision
    |    a               b               c              d         |
    |----------|-----+--------------|---------|-------------------|
                     ↑
                     cf

    For a number cf in the range [0, 2 ** precision), dec_statfun must return
    the symbol whose range cf lies in, which in the picture above is b.
    """
    def append(message, symbol):
        start, freq = enc_statfun(symbol)
        return vrans.append(message, start, freq, precision)

    def pop(message):
        cf, pop_fun = vrans.pop(message, precision)
        symbol = dec_statfun(cf)
        start, freq = enc_statfun(symbol)
        assert np.all(start <= cf) and np.all(cf < start + freq)
        return pop_fun(start, freq), symbol
    return append, pop

_uniform_enc_statfun = lambda s: (s, 1)
_uniform_dec_statfun = lambda cf: cf

def Uniform(precision):
    """
    Codec for symbols uniformly distributed over range(1 << precision).
    """
    # TODO: special case this in vectorans.py
    return NonUniform(_uniform_enc_statfun, _uniform_dec_statfun, precision)

def Benford64():
    """
    Simple self-delimiting code for numbers x with

        2 ** 31 <= x < 2 ** 63

    with log(x) approximately uniformly distributed. Useful for coding
    vectorans stack heads.
    """
    length_append, length_pop = Uniform(5)
    x_lower_append, x_lower_pop = Uniform(31)
    def append(message, x):
        message = x_lower_append(message, x & ((1 << 31) - 1))
        x_len = np.uint64(np.log2(x))
        x = x & ((1 << x_len) - 1)  # Rm leading 1
        x_higher_append, _ = Uniform(x_len - 31)
        message = x_higher_append(message, x >> 31)
        message = length_append(message, x_len - 31)
        return message

    def pop(message):
        message, x_len = length_pop(message)
        x_len = x_len + 31
        _, x_higher_pop = Uniform(x_len - 31)
        message, x_higher = x_higher_pop(message)
        message, x_lower = x_lower_pop(message)
        return message, (1 << x_len) | (x_higher << 31) | x_lower
    return append, pop
Benford64 = Benford64()

def repeat(codec, n):
    """
    Repeat codec n times.

    Assumes that symbols is a Numpy array with symbols.shape[0] == n. Assume
    that the codec doesn't change the shape of the ANS stack head.
    """
    append_, pop_ = codec
    def append(message, symbols):
        assert np.shape(symbols)[0] == n
        for symbol in symbols[::-1]:
            message = append_(message, symbol)
        return message

    def pop(message):
        symbols = []
        for i in range(n):
            message, symbol = pop_(message)
            symbols.append(symbol)
        return message, np.asarray(symbols)
    return append, pop

def shape(message):
    head, _ = message
    def _shape(head):
        if type(head) is tuple:
            return tuple(_shape(h) for h in head)
        else:
            return np.shape(head)
    return _shape(head)