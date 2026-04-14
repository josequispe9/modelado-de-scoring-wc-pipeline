vamos a utilizar airflow, rabbitmq y minio para automatizar los scraping que necesitamos que corran todos los días, tenemos disponibles 6 computadoras de administración (8gb ram) y tres computadoras de sistemas (24gb ram)
Tenemos que armar un fronted web para medir y trazar todo el comportamiento de la ejecución de los scraping.

Estos son los scraping principales que tenemos que realizar:


IRIS: (PC servidor)
 -portout: extraer los clientes que se fueron de la compañía hace dos semanas.
 -portin: extraer los clientes que ingresaron a la compañía el dia anterior.

RAPIPAGO: (PC W1 y W2) - con VPN
 -claro_abono: extraer cuanto paga cada cliente, este valor suele actualizarse mensualmente para cada cliente, en este caso se debe tener en cuenta que el precio que paga es relevante si la fecha de extracción es < 1mes.

ENACOM: (PCs administracion) - con VPN
 -clientes_sin_portabilidad: extraer de los clientes sin portabilidad aquellos que esten en Claro.



Los datos generados por estos scraping deben almacenarse localmente de forma temporal y luego hacerse una copia persistente en el bucket de minio adecuado. El código debe poder escalar horizontalmente para incrementar el número de workers de forma dinámica desde el dashboard por eso utilizamos rabbitmq y airflow.

Por ahora guardemos los datos en minio y luego vemos como hacemos para utilizar esta info para el armado de bases.

