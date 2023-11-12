
from mpi4py import MPI
from dolfinx import fem, io, nls, log, mesh, plot
import numpy as np
import pyvista
from ufl import VectorElement,FiniteElement,MixedElement,TestFunction,TrialFunction,split,grad,tr,Identity,inner,dot
from petsc4py.PETSc import ScalarType
import ufl
from dolfinx.io import gmshio

domain, cell_tags, facet_tags = gmshio.read_from_msh("capacitor_malha.msh", MPI.COMM_SELF,0, gdim=2)

"""Function Space"""
# Define function space, scalar
U2 = ufl.VectorElement("Lagrange", domain.ufl_cell(), 1)  # Displacent
P1 = ufl.FiniteElement("Lagrange", domain.ufl_cell(), 1)  # concentrações + - , electric potential
D0 = ufl.FiniteElement("DG", domain.ufl_cell(), 0)
D1 = ufl.FiniteElement("DG", domain.ufl_cell(), 1)

# DOFs
TH = ufl.MixedElement([U2, P1, P1, P1])
ME = fem.FunctionSpace(domain, TH)  # Total space for all DOFs

"""Extraindo os sub espaços do elemento misto e os mapas contendo os graus de liberdade """
num_subs = ME.num_sub_spaces
spaces = []
maps = []
for i in range(num_subs):
    space_i, map_i = ME.sub(i).collapse()
    spaces.append(space_i)
    maps.append(map_i)



"""Aplicando as propriedades dos materiais"""
"""
1 14 "eletrodo_superior_l"
1 15 "gel_superior_l"
1 16 "gel_inferior_l"
1 17 "eletrodo_inferior_l"

1 18 "eletrodo_inferior_r"
1 19 "gel_inferior_r"
1 20 "gel_superior_r"
1 21 "eletrodo_superior_r"

1 29 "eletrodo_sup_cima"
1 30 "eletrodo_inf_baixo"

2 26 "eletrodo_superior"
2 27 "eletrodo_inferior"
2 28 "gel"
"""


"""Extrair as tags da malha"""

def tag(n_tag):
    return cell_tags.find(n_tag)

"Determinação das propriedades de um material "

def mat_features(function_descontinuo, material, constanste):
    space = fem.Function(function_descontinuo)
    for i in range(len(material)):
        space.x.array[material[i]] = np.full_like(material[i], constanste[i], dtype=ScalarType)
    return space


""" Implementação das propriedades em cada regiao"""
Q = fem.FunctionSpace(domain, D0)

eletrodo_sup = tag(26)
eletrodo_inf = tag(27)
gel_p = tag(28)

# A ordem de entrada das propriedades na lista deve ser equivalente ao espaço no qual o material ocupa dentro do dominio
material_ = [gel_p, eletrodo_inf, eletrodo_sup]
Gshear = mat_features(Q, material_, [0.003e-6, 0.034e-6, 0.2e-6])
Kbulk = mat_features(Q, material_, [2000 * 0.003e-6, 2000 * 0.034e-6, 2000.0 * 0.2e-6])
intInd = mat_features(Q, material_, [1, 0, 0])
matInd = mat_features(Q, material_, [1, 0, 0])
Gshear0 = 100.0e-6  # uso na formução fraca e no cconstrutor
Im_gent = mat_features(Q, material_, [300, 90.0, 90.0])

"""Constantes"""
D = 1.0e-2  # 1.0e0                 # Diffusivity [L2T-1]
RT = 8.3145e-3 * (273.0 + 20.0)  # Gas constant*Temp [ML2T-2#-1]
Farad = 96485.0e-6  # Faraday constant [Q#-1]

""" Initial concentrations"""
cPos0 = 0.274  # Initial concentration [#L-3]
cNeg0 = cPos0  # Initial concentration [#L-3]
cMax = 10000 * 1e-9  # 0.00001*1e-9 # 10000e0*1.e-9

"""Eletrical permittivity """
vareps0 = fem.Constant(domain, 8.85e-12 * 1e-6)  #
vareps_num = mat_features(Q, material_, [1.0e4, 1.0, 1.0])  # Permissividade do gel igual a 10000
vareps_r = mat_features(Q, material_, [80, 6.5, 6.5])  # eletrical permittivity for material
vareps = vareps0 * vareps_r * vareps_num

# Mass density
rho = 1e-9  # 1e3 kg/m^3 = 1e-9 mg/um^3,

# Rayleigh damping coefficients
eta_m = 0.00000  # Constant(0.000005)
eta_k = 0.00000  # Constant(0.000005)


""" Generalized-alpha method parameters """
alpha = 0.0
gamma = 0.5 + alpha
beta = ((gamma + 0.5) ** 2) / 4


""" Simulation time related params (reminder: in microseconds)"""
ttd = 0.01
# Step in time
t = 0.0  # initialization of time
T_tot = 0e6 * 1.0e6  # 200.0 #0.11        # total simulation time

#

t1 = 15.0e6  # sem uso
t2 = 35.0e6  # sem uso
t3 = 2.5e6  # sem uso
t4 = 52.5e6  # sem uso


T2_tot = 30.0e6  # 0.0001*1.e6 #t1+t2+t3+t4
dt = T2_tot / 500  # incrementos de tempo

phi_norm = RT / Farad  # "Thermal" Volt























(u_test, omgPos_test, phi_test, omgNeg_test)  = ufl.TestFunctions(ME)    # Test function 

# Define test functions in weak form
dw = ufl.TrialFunction(ME)

# Define actual functions with the required DOFs
w = fem.Function(ME)
(u, omgPos, phi, omgNeg) = ufl.split(w)  # current DOFs

# A copy of functions to store values in last step for time-stepping.
w_old = fem.Function(ME)
(u_old, omgPos_old, phi_old, omgNeg_old) = ufl.split(w_old)  # old DOFs

"""Duvida sobre a implementação desse U2"""
W2 = fem.FunctionSpace(domain, U2)
v_old = fem.Function(W2)
a_old = fem.Function(W2)

# Initial chemical potential
mu0 = ufl.ln(cPos0)
mu20 = ufl.ln(cNeg0)


"""Concentrações iniciais"""
x = ufl.SpatialCoordinate(domain)

DOlfin_Eps= 0.3e-16
scaleY = 900.e0 #Problema aqui
tol = 1e-12

int1 = 200.e0 # 
int2 = scaleY/2.-int1

class init_Omg:
    def __init__(self):
        self.scaley= scaleY
        self.int2= int2
        self.tol= tol
        self.c= 0
        self.CNum= DOlfin_Eps
        
    def init_Omg_eval():
        pass
       
# Initial electro-chemical potentials
#init_omgPos = Expression('abs(x[1])>=int2-tol?std::log((cPos0)):std::log((cNum))', int2=int2, tol = tol, cPos0 = cPos0, cNum=DOLFIN_EPS, degree=0)


#my_bc_value = init_Omg()
#my_bc_value.c=cPos0
#value_function = fem.Function(spaces[1])
#bc_expr = fem.Expression(my_bc_value, spaces[1].element.interpolation_points())
#w_old.sub(1).interpolate(bc_expr)































"""Bondary condition """
fdim = domain.topology.dim - 1

def fixed_displacement_expression(x):
    return np.stack((np.zeros(x.shape[1]), np.zeros(x.shape[1])))

fixed_displacement = fem.Function(spaces[0])
fixed_displacement.interpolate(fixed_displacement_expression)

"""
1 14 "eletrodo_superior_l"
1 15 "gel_superior_l"
1 16 "gel_inferior_l"
1 17 "eletrodo_inferior_l"

1 18 "eletrodo_inferior_r"
1 19 "gel_inferior_r"
1 20 "gel_superior_r"
1 21 "eletrodo_superior_r"

1 29 "eletrodo_sup_cima"
1 30 "eletrodo_inf_baixo"

2 26 "eletrodo_superior"
2 27 "eletrodo_inferior"
2 28 "gel"


"""
"""V.sub(0) is a view into the sub space of a space with multiple elements. It contains all degrees of freedom in the mixed space.
V.sub(0).collapse() (in your case Q) is a function space with only the dofs in the sub-space.
To map from a function in Q to a function in V.sub(0) , one supply the tuple, as it will then give a row by row map between the degrees of freedom.

This map (dofs_top) is used inside a Dirichlet condition that takes in a prescribed function q in Q, that you want to prescribe to your solution (say w) in V.

"""
"""Engaste"""
Engast_0 = fem.locate_dofs_topological((ME.sub(0), spaces[0]), fdim, facet_tags.find(14))
Engast0 = fem.dirichletbc(fixed_displacement, Engast_0, ME.sub(0))

Engast_1 = fem.locate_dofs_topological((ME.sub(0), spaces[0]), fdim, facet_tags.find(15))
Engast1 = fem.dirichletbc(fixed_displacement, Engast_1, ME.sub(0))

Engast_2 = fem.locate_dofs_topological((ME.sub(0), spaces[0]), fdim, facet_tags.find(16))
Engast2 = fem.dirichletbc(fixed_displacement, Engast_2, ME.sub(0))

Engast_3 = fem.locate_dofs_topological((ME.sub(0), spaces[0]), fdim, facet_tags.find(17))
Engast3 = fem.dirichletbc(fixed_displacement, Engast_3, ME.sub(0))

"""Estiramento : Deve-se alterar para obter os valores ideais de estiramento"""
scaleX = 1.0e4  #Tem que arrumar isso, valor incorreto

class disp_Exp:
    def __init__(self):
        self.t= 0.0
        self.Tramp =T2_tot
        self.scalex = scaleX
    
    def eval(self,x):
     #   return np.stack((np.zeros(x.shape[1]), np.full(x.shape[1], 5.5*self.scalex*self.t/self.Tramp)))
        return np.stack((np.full(x.shape[1], 5.5*self.scalex*self.t/self.Tramp), np.zeros(x.shape[1])))
dispV= disp_Exp()
dispV.t= 0.
dispV.Tramp= T2_tot
dispV.scalex= scaleX
disp= fem.Function(spaces[0])
disp.interpolate(dispV.eval)

stretch00= fem.locate_dofs_topological((ME.sub(0).sub(0),spaces[0]),fdim,facet_tags.find(18)) 
bc_stretch0= fem.dirichletbc(disp, stretch00, ME.sub(0))

stretch01= fem.locate_dofs_topological((ME.sub(0).sub(0),spaces[0]),fdim,facet_tags.find(19)) 
bc_stretch1= fem.dirichletbc(disp, stretch01, ME.sub(0))

stretch02= fem.locate_dofs_topological((ME.sub(0).sub(0),spaces[0]),fdim,facet_tags.find(20)) 
bc_stretch2= fem.dirichletbc(disp, stretch02, ME.sub(0))

stretch03= fem.locate_dofs_topological((ME.sub(0).sub(0),spaces[0]),fdim,facet_tags.find(21)) 
bc_stretch3= fem.dirichletbc(disp, stretch03, ME.sub(0))


"""Aterramento"""
def ground_0(x):
    return np.stack((np.zeros(x.shape[1])))

ground = fem.Function(spaces[2])
ground.interpolate(ground_0)

ground0 = fem.locate_dofs_topological((ME.sub(2), spaces[2]), fdim, facet_tags.find(30))
bc_ground = fem.dirichletbc(ground, ground0, ME.sub(2))


"""Aplicação da voltagem inicial de 0 à 1, em um intervalo de 30s, e permanecer constante em 1 indefinidamente """
class phiRamp_function():
    def __init__(self):
        self.phi_norm= phi_norm
        self.pi=np.pi
        self.Tramp= 30.0e6
        self.t= 0.0
        self.temp= 1.0e3
        
    def phi_eval(self,x):
        return np.stack((np.full(x.shape[1], min(self.temp/self.phi_norm*(self.t/self.Tramp), self.temp/self.phi_norm))))

phiRamp_func= phiRamp_function()
phiRamp_func.t= 0.0
phiRamp= fem.Function(spaces[2])
phiRamp.interpolate(phiRamp_func.phi_eval)

phiRamp_0= fem.locate_dofs_topological((ME.sub(2),spaces[2]),fdim,facet_tags.find(29))
bc_phiRamp = fem.dirichletbc(phiRamp,phiRamp_0,ME.sub(2))

bc=[Engast0,Engast1,Engast2,Engast3, bc_stretch0,bc_stretch1,bc_stretch2,bc_stretch3, bc_ground,bc_phiRamp  ]


"""Vizualização das condições de contorno"""

from dolfinx.io import XDMFFile
with XDMFFile(MPI.COMM_WORLD, "resultados/un.xdmf", "w") as ufile_xdmf:
        ground.x.scatter_forward()
        ufile_xdmf.write_mesh(domain)
        ufile_xdmf.write_function(ground)
        ufile_xdmf.write_meshtags(facet_tags)
        ufile_xdmf.write_meshtags(cell_tags)
    
with XDMFFile(MPI.COMM_WORLD, "resultados/An.xdmf", "w") as pfile_xdmf:
        disp.x.scatter_forward()
        pfile_xdmf.write_mesh(domain)
        pfile_xdmf.write_meshtags(facet_tags)
        pfile_xdmf.write_meshtags(cell_tags)
        pfile_xdmf.write_function(disp)  