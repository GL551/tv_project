#!/usr/bin/python

import numpy as np
import scipy.optimize as opt
import warnings

from complex_roots import RootFinderRectangle

class TerminalVelocitySolver():
    def __init__(self,
                 dust_gas_ratio,
                 wave_number_x,
                 wave_number_z,
                 minimum_stopping_time,
                 maximum_stopping_time,
                 power_law_exponent_size_distribution,
                 maximum_iterations=100):
        # Dust fraction
        self.fd = dust_gas_ratio/(1.0 + dust_gas_ratio)

        self.kx = wave_number_x
        self.kz = wave_number_z

        # tau_max is fixed, tau_min is array
        self.tau_min = minimum_stopping_time
        self.tau_max = maximum_stopping_time

        # b = 1/2 = MRN
        # supported values: -3, -3.5, -4.5, -5.5
        self.b = -(3 + power_law_exponent_size_distribution)
        # Call I2 just to check if it likes the value of b,
        # the calls from the root finder catch errors
        res = self.I2(1.0, 2.0)

        self.max_it = maximum_iterations

    # Complex arctan
    def atanc(self, z):
        return 0.5*1j*(np.log(1 - 1j*z) - np.log(1 + 1j*z))

    # (1 - I2)/z
    def I2(self, z, s):
        s1 = np.power(s, 1 - self.b)
        s2 = np.power(s, 2 - self.b)

        w = z*(self.b - 1)*(1 - s2)/((self.b - 2)*(1 - s1))

        arg = (1 - np.sqrt(s))/(np.sqrt(w) + np.sqrt(s/w))

        if self.b == 0.5:
            return  1 - np.sqrt(w)*self.atanc(arg)/(1 - np.sqrt(s))
        elif self.b == 1.5:
            return -self.atanc(arg)/(np.sqrt(w)*(1 - s1))
        elif self.b == 2.5:
            return (1 + self.atanc(arg)/(np.sqrt(w)*(1 - s2)))/z
        elif self.b == 0.0:
            return 1 - w*np.log((w + 1)/(w + s))/(1 - s)
        else:
            raise NotImplementedError(('No form for the I2 integral for this'
                                       ' parameter b {:e}').format(self.b))

    # Secular mode single size at tau = tau_max, use as starting point
    def single_size_z(self):
        # Cubic dispersion relation
        k2 = self.kx*self.kx + self.kz*self.kz
        fg = 1 - self.fd

        a = 1
        b = (2*fg*fg*self.kx + 1j*self.fd)*self.tau_max
        c = -self.kz**2/k2
        d = 2*fg*(self.fd - fg)*self.kz**2*self.kx*self.tau_max/k2

        roots = np.roots([a, b, c, d])

        w = roots[np.argmax(np.imag(roots))]

        z = (w - 2*fg*self.fd*self.tau_max*self.kx)/(2*fg*self.kx*self.tau_max)
        return z

    def average_tau(self, s):
        s = s*s/(s + 1.0e-10)

        s1 = (self.b - 1)*(1 - s**(self.b-2))
        s2 = (self.b - 2)*(1 - s**(self.b-1))

        return s*self.tau_max*s1/s2

    # Dispersion relation of which we need to find roots
    def func(self, z, s):
        tau = self.average_tau(s)
        fg = 1 - self.fd

        omega = 2*fg*self.kx*tau*(z + self.fd)
        k2 = self.kx*self.kx + self.kz*self.kz
        A = 2*fg*k2*tau*tau*self.kx/(self.kz*self.kz)

        # Dispersion relation: lhs = fac*fac2
        lhs = 1.0 - k2*omega*omega/(self.kz*self.kz)

        fac = self.fd*(1j*A*np.power(z + self.fd, 2) + 1)
        fac2 = self.I2(z, s)

        return fac*fac2 - lhs

    # Find root at s = s_want, given that we know solution at s_start
    def find_root(self, s_want, s_start, z_start):
        delta_s = 0.1
        s_current = s_start
        z = z_start

        n_iter = 0
        while s_current > s_want:
            n_iter += 1
            if n_iter > self.max_it:
                s_current = s_want
                print('Warning: maximum iterations reached at z = ',
                      z, ', assuming z=0')
                z = 0
                break

            s = s_current - delta_s

            if s < s_want:
                s = s_want

            error_flag = 0
            try:
                f = lambda z: self.func(z, s)
                z = opt.newton(f, z_start)
            except ValueError:
                error_flag = 1
                z = z_start
            except RuntimeError:
                error_flag = 1
                z = z_start

            if (np.imag(z) < 0 or
                    error_flag == 1 or
                    np.imag(z) > 0.5 or
                    np.isnan(np.imag(z))):
                delta_s = 0.1*delta_s
            else:
                #print(n_iter, np.log10(s*self.tau_max), z)

                delta_s = np.sqrt(2)*delta_s
                s_current = s
                z_start = z

        return z

    # Find roots of dispersion relation for all tau_min
    def find_roots(self):
        N = len(self.tau_min)
        z = np.zeros(N, dtype=np.complex128)

        # s = tau_min/tau_max
        s_start = 1.0
        # Start at single size solution at s = 1
        z0 = self.single_size_z()

        # Work towards smaller s
        for j in range(0, N):
            s_want = self.tau_min[N - 1 - j]/self.tau_max
            z[N - 1 - j] = self.find_root(s_want, s_start, z0)
            s_start = s_want
            z0 = z[N - 1 - j]
            if z0 == 0:
                break

        tau = self.average_tau(self.tau_min/self.tau_max)

        #print('Final growth rate w:', self.kx*tau*(z + self.fd))
        return 2*(1 - self.fd)*self.kx*tau*(z + self.fd)



class PSIModeTV():
    """Terminal velocity PSI mode

    Calculate mode frequency for a PSI mode in the terminal velocity approximation for power law size distributions. Initialize with a dust to gas ratio, a maximum Stokes number and a power law exponent of the size distribution. Calculate for specific wave numbers and minimum Stokes numbers.

    Args:
        dust_gas_ratio: Dust to gas ratio
        maximum_stokes: Maximum Stokes number in the size distribution
        power_law_exponent_size_distribution (optional): power law exponent of the size distribution. The default, -3.5, represents the MRN size distribution.
        maximum_iterations (optional): maximum secant steps to take before giving up and declaring that the mode does not exist.
    """
    def __init__(self,
                 dust_gas_ratio,
                 maximum_stokes,
                 power_law_exponent_size_distribution=-3.5,
                 maximum_iterations=100):
        # Dust fraction
        self.fd = dust_gas_ratio/(1 + dust_gas_ratio)
        # Maximum stopping time
        self.tau_max = maximum_stokes

        # b = 1/2 = MRN
        # supported values: -3, -3.5, -4.5, -5.5
        self.b = -(3 + power_law_exponent_size_distribution)
        # Call I2 just to check if it likes the value of b,
        # the calls from the root finder catch errors
        res = self.F_integral(1.0, 0.1)

        self.max_it = maximum_iterations

    def atanc(self, z):
        """Complex arctan"""
        return 0.5*1j*(np.log(1 - 1j*z) - np.log(1 + 1j*z))

    def F_integral(self, z, s):
        """Calculate the F integral, or, actually F(z)/(1+z)"""

        if 1 - s < 1.0e-12:
            return 1/(1 + z)

        s1 = np.power(s, 1 - self.b)
        s2 = np.power(s, 2 - self.b)

        w = z*(self.b - 1)*(1 - s2)/((self.b - 2)*(1 - s1 + 1.0e-30))

        arg = (1 - np.sqrt(s))/(np.sqrt(w) + np.sqrt(s/w))

        if self.b == 0.5:    # n = 0
            return 1 - np.sqrt(w)*self.atanc(arg)/(1 - np.sqrt(s))
        elif self.b == 1.5:  # n = 1
            return -self.atanc(arg)/(np.sqrt(w)*(1 - s1))
        elif self.b == 2.5:  # n = 2
            return (1 + self.atanc(arg)/(np.sqrt(w)*(1 - s2)))/z

        elif self.b == 0.0:
            return 1 - w*np.log((w + 1)/(w + s))/(1 - s)
        elif ((2*self.b).is_integer() == True and (self.b).is_integer() == False):
            # n needs to be an integer!
            n = self.b - 0.5

            ret = 2*np.power(-1.0, n+1)*np.exp((0.5-n)*np.log(w))*self.atanc(arg)
            ret = ret + (1 - np.power(s, 1.5 - n))/(1.5 - n)/w

            if n < 2:
                k = np.arange(0, 2-n)
                a = np.power(-1.0, k)*(1 - np.power(s, 1.5 - n - k))*np.exp((k-1)*np.log(w))/(1.5 - n - k)
                ret = ret - np.sum(a)
            if n > 2:
                k = np.arange(-1, 3-n)
                a = np.power(-1.0, k)*(1 - np.power(s, 1.5 - n - k))*np.exp((k-1)*np.log(w))/(1.5 - n - k)
                ret = ret + np.sum(a)

            return ret*(0.5 - n)/(1 - np.power(s, 0.5-n))
        else:
            raise NotImplementedError(('No form for the I2 integral for this'
                                       ' parameter b {:e}').format(self.b))

    def omega_to_z(self, w, tau, Kx, Kz):
        fg = 1 - self.fd
        K2 = Kx**2 + Kz**2
        fac = 2*fg*tau*Kx
        return (w - self.fd*fac + 1j*self.D*K2)/fac

    def z_to_omega(self, z, tau, Kx, Kz):
        fg = 1 - self.fd
        K2 = Kx**2 + Kz**2
        fac = 2*fg*tau*Kx

        return fac*(z + self.fd) - 1j*self.D*K2

    # Secular mode single size at tau = tau_max, use as starting point
    def single_size_z(self, Kx, Kz):
        """Calculate growing mode in the single size limit, to be used as a starting point when searching for a PSI root"""
        K2 = Kx*Kx + Kz*Kz

        # Gas fraction
        fg = 1 - self.fd

        # Coefficients of cubic dispersion relation
        a = 1
        b = (2*fg*fg*Kx + 1j*self.fd)*self.tau_max + 1j*self.D*K2
        c = self.fd*self.tau_max*self.D*K2 - Kz**2/K2
        d = 2*fg*(self.fd - fg)*Kz**2*Kx*self.tau_max/K2 - 1j*self.D*Kz**2

        # Roots of 3rd order polynomial
        roots = np.roots([a, b, c, d])

        # Root with maximum imaginary part
        w = roots[np.argmax(np.imag(roots))]

        # Convert from w to z
        #z = (w - 2*fg*self.fd*self.tau_max*Kx)/(2*fg*Kx*self.tau_max)
        return self.omega_to_z(w, self.tau_max, Kx, Kz)

    def average_tau(self, s):
        """Average stopping time"""
        # Make sure no division by zero
        s = s*s/(s + 1.0e-10)

        s1 = (self.b - 1)*(1 - s**(self.b-2))
        s2 = (self.b - 2)*(1 - s**(self.b-1))

        return s*self.tau_max*s1/s2

    def disp(self, z, s, Kx, Kz):
        """Dispersion relation"""
        # Make sure we can handle scalar and vector input.
        z = np.asarray(z)
        scalar_input_z = False
        if z.ndim == 0:
            z = z[None]  # Makes z 1D
            scalar_input_z = True
        else:
            original_shape_z = np.shape(z)
            z = np.ravel(z)

        tau = self.average_tau(s)
        fg = 1 - self.fd

        omega = self.z_to_omega(z, tau, Kx, Kz)

        K2 = Kx*Kx + Kz*Kz

        # Dispersion relation: lhs = fac*fac2
        lhs = 1.0 - K2*omega**2/Kz**2

        fac = self.fd*(1j*omega*tau*K2*(z + self.fd)/Kz**2 + 1)

        fac2 = 0.0*z
        for i in range(0, len(z)):
            fac2[i] = self.F_integral(z[i], s)

        ret = fac*fac2 - lhs

        # Return value of original shape
        if scalar_input_z:
            return np.squeeze(ret)
        return np.reshape(ret, original_shape_z)


    def find_root(self, s_want, s_start, z_start, Kx, Kz, verbose=False):
        """Find a root at s = tau_min/tau_max = s_want, given that we know the solution at s_start > s_want, which is z_start"""
        # Step in s
        delta_s = 0.1
        s_current = s_start
        z = z_start

        n_iter = 0
        while s_current > s_want:
            n_iter += 1
            if n_iter > self.max_it:
                s_current = s_want
                if verbose is True:
                    print('Warning: maximum iterations reached at z = ',
                          z, ', assuming z=0')
                z = 0
                break

            s = s_current - delta_s

            # Make sure to end exactly on s_want
            if s < s_want:
                s = s_want

            error_flag = 0
            try:
                # Try to find root of dispersion relation, starting at z_start
                f = lambda z: self.disp(z, s, Kx, Kz)
                z = opt.newton(f, z_start)
            except ValueError:
                # On error, reject step
                error_flag = 1
                z = z_start
            except RuntimeError:
                error_flag = 1
                z = z_start

            # Reduce step size if root rejected
            if (np.imag(z) < -1.0e-10 or
                error_flag == 1 or
                np.imag(z) > 0.5 or
                np.isnan(np.imag(z))):
                #print('Root rejected:', z, s, error_flag)
                delta_s = 0.1*delta_s
            else:
                #print('Root accepted:', z, s)
                # Accept root, increase step
                delta_s = np.sqrt(2)*delta_s
                s_current = s
                z_start = z

        return z

    # Find roots of dispersion relation for all tau_min
    def find_roots(self, minimum_stokes, Kx, Kz,
                   viscous_alpha=0, c_over_eta=20, verbose=False):
        """Find roots of dispersion relation.

        Args:
            minimum_stokes: Minimum Stokes number of size distribution. Values must be sorted in ascending order.
            Kx: Dimensionless wave number in x
            Kz: Dimensionless wave number in z
        """

        # Dust diffusion coefficient
        self.D = viscous_alpha*c_over_eta**2

        # Make sure we can handle scalar and vector input.
        tau_min = np.asarray(minimum_stokes)
        scalar_input_tau_min = False
        if tau_min.ndim == 0:
            tau_min = tau_min[None]  # Makes z 1D
            scalar_input_tau_min = True
        else:
            original_shape_tau_min = np.shape(minimum_stokes)
            tau_min = np.ravel(minimum_stokes)

        z = np.zeros(np.shape(tau_min), dtype=np.complex128)
        # Work through tau_min array in reverse order
        idx = np.flip(np.arange(len(tau_min)))

        # s = tau_min/tau_max
        s_start = 1.0
        # Start at single size solution at s = 1
        z0 = self.single_size_z(Kx, Kz)

        # Work towards smaller s
        for j in idx:
            s_want = tau_min[j]/self.tau_max
            z[j] = self.find_root(s_want, s_start, z0, Kx, Kz, verbose=verbose)
            s_start = s_want
            z0 = z[j]
            if z0 == 0:
                break

        # Convert from z to omega
        tau = self.average_tau(tau_min/self.tau_max)

        ret = self.z_to_omega(z, tau, Kx, Kz)

        if scalar_input_tau_min:
            return np.squeeze(ret)

        return np.reshape(ret, original_shape_tau_min)


    # Find roots of dispersion relation for all tau_min
    def find_roots_new(self, minimum_stokes, Kx, Kz,
                   viscous_alpha=0, c_over_eta=20, verbose=False):
        """Find roots of dispersion relation.

        Args:
            minimum_stokes: Minimum Stokes number of size distribution. Values must be sorted in ascending order.
            Kx: Dimensionless wave number in x
            Kz: Dimensionless wave number in z
        """

        # Dust diffusion coefficient
        self.D = viscous_alpha*c_over_eta**2

        # Make sure we can handle scalar and vector input.
        tau_min = np.asarray(minimum_stokes)
        scalar_input_tau_min = False
        if tau_min.ndim == 0:
            tau_min = tau_min[None]  # Makes z 1D
            scalar_input_tau_min = True
        else:
            original_shape_tau_min = np.shape(minimum_stokes)
            tau_min = np.ravel(minimum_stokes)

        z = np.zeros(np.shape(tau_min), dtype=np.complex128)
        # Work through tau_min array in reverse order
        idx = np.flip(np.arange(len(tau_min)))

        rc = RootFinderRectangle(real_range=[-1.0, 1.0],
                                 imag_range=[1.0e-8, 1.0],
                                 n_sample=10,
                                 max_zoom_domains=2,
                                 verbose_flag=False,
                                 tol=1.0e-13,
                                 clean_tol=1.0e-4,
                                 max_secant_iterations=100)

        # Work towards smaller s
        for j in idx:
            func = lambda x: self.disp(x, tau_min[j]/self.tau_max, Kx, Kz)

            res = rc.calculate(func, guess_roots=[])
            #print('Res: ', res)
            if len(res) > 0:
                z[j] = res[0]

        # Convert from z to omega
        tau = self.average_tau(tau_min/self.tau_max)

        ret = self.z_to_omega(z, tau, Kx, Kz)

        if scalar_input_tau_min:
            return np.squeeze(ret)

        return np.reshape(ret, original_shape_tau_min)
