from dolfinx import fem
import ufl
from petsc4py.PETSc import ScalarType
from dolfinx import fem,log, nls ,mesh
from dolfinx.io import gmshio
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

# Scaled variable
carregamento= 1 #-5000
E = 1# 78e6
poisson = 1# 0.3
lambda_ =  1 #E*poisson / ((1+poisson)*(1-2*poisson))
G= 1#E / 2*(1+poisson)



domain = mesh.create_rectangle(comm=MPI.COMM_WORLD,
                            points=((0.0, 0.0), (2.0, 1.0)), n=(300, 300),
                            cell_type=mesh.CellType.triangle,)

V = fem.VectorFunctionSpace(domain, ("CG", 1))

def clamped_boundary(x):
    return np.isclose(x[0], 0)

fdim = domain.topology.dim - 1
boundary_facets = mesh.locate_entities_boundary(domain, fdim, clamped_boundary)

u_D = np.array([0,0], dtype=ScalarType)
bc = fem.dirichletbc(u_D, fem.locate_dofs_topological(V, fdim, boundary_facets), V)

#Aproximação das funções teste e funcao incognita
v = ufl.TestFunction(V)
u= fem.Function(V)
uh = ufl.TrialFunction(V)

#hencky's strain tensor
d = len(u)
I = (ufl.Identity(d)) 
F =(I + ufl.grad(u)) 
#tensor de cauchy-Green left 
C= (F * F.T )

#determinando o Jacobiano
Jhc_e= ufl.det(F)
J= Jhc_e

#Hencky's Strain
N, M = C.ufl_shape
T_hencky=ufl.as_tensor([[(1/2)*(ufl.ln(C[i,j])) for i in range(N)] for j in range(M)])


#Tensor de tensões
def T_tension(u):
    oo = len(u)
    o = (ufl.Identity(oo)) 
    return (1/J)*(2.0 * G * T_hencky + lambda_ * ufl.tr(T_hencky) * o )


#Funcao carregamento = f(0,y)
f = fem.Constant(domain,ScalarType((0,carregamento)))

ds = ufl.Measure("ds", domain=domain)


#Formulação variacional para Div T = 0, em Tn= f,u= 0 em x=0
#Weak form for  Div T = 0,  Tn= f, u= 0 in 
F_bilinear = ufl.inner(ufl.grad(v),T_tension(u))*ufl.dx - ufl.inner(f, v)*ds



#Formulação variacional para Div T = 0, em Tn= f,u= 0 in facet_tags.find(16)
problem = fem.petsc.NonlinearProblem(F=F_bilinear ,u=u,bcs=[bc])


#solucao não linear 
solver = nls.petsc.NewtonSolver(MPI.COMM_WORLD, problem)

solver.convergence_criterion = "residual"
solver.rtol = 1e-8
solver.atol = 1e-8
solver.max_it = 100
solver.report = True


#solver.solver_type = "gmres"
#solver.preconditioner_type = "lu"
solver.initial_guess = None  # Pode ser um vetor ou None
#solver.divergence_tolerance = 
#solver.monitor = None  # Pode ser uma função de monitoramento personalizada
solver.line_search = True
#solver.jacobian_update = "approximate"

#vizualização 

#solver_krylov = solver.krylov_solver
#solver_krylov.setType("preonly")
#solver_krylov.getPC().setType("lu")
#solver.error_on_nonconvergence = True

log.set_log_level(log.LogLevel.INFO)
n, converged = solver.solve(u)
solver.view()
#assert(converged)
#print(f"Number of interations: {n:d}")
